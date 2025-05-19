import abc
from pathlib import Path
from typing import ClassVar, Sequence, TypeVar

from msgspec import convert

from lihil.config.app_config import AppConfig
from lihil.config.parser import build_parser, format_nested_dict
from lihil.errors import AppConfiguringError
from lihil.interface import StrDict, is_provided
from lihil.utils.algorithms import deep_update

TConfig = TypeVar("TConfig", bound=AppConfig)


class UnsupportedFileFormatError(AppConfiguringError):
    def __init__(self, file: Path, message: str):
        super().__init__(
            f"File {file} can't be loaded, as required dependency is not installed, {message}"
        )


class MissingLoaderError(AppConfiguringError):
    def __init__(self, format: str):
        super().__init__(f"Loader for {format} is not found")


class LoaderNode(abc.ABC):
    @abc.abstractmethod
    def _validate(self, file: Path) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def loads(self, file: Path) -> StrDict:
        raise NotImplementedError


class LoaderBase(LoaderNode):
    supported_formats: ClassVar[set[str] | str]

    def __init__(self) -> None:
        self._next: "LoaderBase | None" = None

    def __str__(self):
        return f"{self.__class__.__name__}({self.supported_formats})"

    def __repr__(self):
        return self.__str__()

    @property
    def next(self) -> "LoaderBase | None":
        return self._next

    @next.setter
    def next(self, handler: "LoaderBase | None") -> None:
        self._next = handler

    def validate(self, file: Path) -> bool:
        if not file.is_file() or not file.exists():
            raise FileNotFoundError(f"File {file} not found at {Path.cwd()}")
        return self._validate(file)

    def _validate(self, file: Path) -> bool:
        supported = self.supported_formats
        if isinstance(supported, str):
            supported = {supported}
        return file.suffix in supported or file.name in supported

    def handle(self, file: Path) -> StrDict:
        if self.validate(file):
            try:
                return self.loads(file)
            except ImportError as ie:
                raise UnsupportedFileFormatError(file, str(ie)) from ie
        else:
            if self._next is None:
                raise MissingLoaderError(file.suffix)
            return self._next.handle(file)

    def chain(self, handler: "LoaderBase") -> "LoaderBase | None":
        if self._next is None:
            self._next = handler
            return self._next

        return self._next.chain(handler)

    def reverse(self) -> None:
        """
        Reverse the whole chain so that the last node becomes the first node
        Do this when you want your newly added subclass take over the chain
        """
        prev = None
        node = self

        while node.next:
            next = node.next
            node.next = prev
            prev = node
            node = next

        node.next = prev

    @classmethod
    def chainup(cls) -> "LoaderBase":
        head = ptr = None
        for sub_cls in reversed(cls.__subclasses__()):
            node = sub_cls()
            if head is None or ptr is None:
                head = ptr = node

            ptr.next = node
            ptr = ptr.next

        assert head
        return head


class ENVFileLoader(LoaderBase):
    supported_formats = ".env"

    def loads(self, file: Path) -> StrDict:
        import dotenv

        return dotenv.dotenv_values(file)


class TOMLFileLoader(LoaderBase):
    supported_formats = ".toml"

    def loads(self, file: Path) -> StrDict:
        try:
            import tomllib as tomli  # tomllib available ^3.11
        except ImportError:
            import tomli

        try:
            config = tomli.loads(file.read_text())["lihil"]
        except KeyError:
            raise AppConfiguringError(f"Can't find table `lihil` in {file}")
        return config


# class YAMLFileLoader(LoaderBase):
#     supported_formats = {".yml", ".yaml"}

#     def loads(self, file: Path) -> StrDict:
#         import yaml
#         config: StrDict = yaml.safe_load(file.read_bytes())
#         return config


# class JsonFileLoader(LoaderBase):
#     supported_formats = ".json"

#     def loads(self, file: Path) -> StrDict:
#         import json

#         config: StrDict = json.loads(file.read_bytes())
#         return config


def load_from_cli(
    args: Sequence[str] | None = None, *, config_type: type[AppConfig]
) -> StrDict | None:
    parser = build_parser(config_type)

    known_args, _ = parser.parse_known_args(args)  # _ is unkown args
    parsed_args = known_args.__dict__

    # Filter out _provided flags and keep only provided values
    cli_args: StrDict = {k: v for k, v in parsed_args.items() if is_provided(v)}

    if not cli_args:
        return None

    config_dict = format_nested_dict(cli_args)
    return config_dict


class ConfigLoader:
    def __init__(self, work_dir: Path | str | None = None):
        work_dir = Path(work_dir) if isinstance(work_dir, str) else work_dir
        self.work_dir = work_dir or Path.cwd()
        self.loader = LoaderBase.chainup()

    def __repr__(self):
        return f"{self.__class__.__name__}(work_dir={self.work_dir})"

    def load_files(self, *files: str | Path) -> StrDict:
        result: StrDict = {}
        for f in files:
            f = Path(f) if isinstance(f, str) else f
            if not f.exists():
                raise AppConfiguringError(
                    f"path {f} not exist in current dir {self.work_dir}"
                )
            data = self.loader.handle(f)
            deep_update(result, data)
        return result

    def load_config(
        self, *config_files: Path | str, config_type: type[TConfig] = AppConfig
    ) -> TConfig | None:
        config_dict = self.load_files(*config_files)
        cli_config = load_from_cli(config_type=config_type)
        if cli_config:
            deep_update(config_dict, cli_config)
        if not config_dict:
            return None
        config = convert(config_dict, config_type)
        return config
