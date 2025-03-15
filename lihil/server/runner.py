# import sys

# from loguru import logger

# from lihil.config import ServerConfig
# from lihil.interface import ASGIApp
# from lihil.server.server import LihilInterface, Server

# # from argparse import ArgumentParser

# # TODO: rename to cli, move to core or root dir


# def run(app: ASGIApp, *, host: str = "127.0.0.1", port: str = "8000") -> None:
#     "entry of the program"
#     config = ServerConfig(host=host, port=int(port))
#     server = Server(app, config=config)

#     try:
#         server.run()
#     except KeyboardInterrupt:
#         logger.info("Closing app by ^C")
#         sys.exit(0)

#     if not server.started:
#         sys.exit(3)
