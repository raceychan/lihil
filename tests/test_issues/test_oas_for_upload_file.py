from typing import Annotated

from lihil import Form, Lihil, UploadFile


async def music(file: UploadFile): ...


async def upload_many(
    files: Annotated[
        list[UploadFile], Form(max_files=5, max_part_size=2 * 1024 * 1024)
    ],
) -> int:
    return len(files)


async def test_generate_oas_for_music_ep():
    lhl = Lihil()
    lhl.post(music)

    lhl.genereate_oas()
