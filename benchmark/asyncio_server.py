import asyncio
from asyncio import StreamReader, StreamWriter

import uvloop

# from .share import endpoint


async def handle_client(reader: StreamReader, writer: StreamWriter):
    while True:
        try:
            # Read the full request data
            request_data = await reader.read(1024)
            if not request_data:
                break

            req = request_data.split(b"\r\n")
            method, host, user_agent, *_, content_length, body = req

            # Process the request and get response data
            # body = endpoint(body)
            body = "hello, world".encode()

            # Create and send the response with the body
            response = (
                "HTTP/1.1 200 OK\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Content-Type: application/json\r\n"
                "Connection: keep-alive\r\n"  # Keep the connection alive
                "\r\n"
            ).encode() + body

            writer.write(response)
            await writer.drain()
        except Exception:
            # Only close on error
            writer.close()
            await writer.wait_closed()
            break


async def main():
    port = 8000
    print(f"asyncio server started at {port}")
    server = await asyncio.start_server(handle_client, "127.0.0.1", port)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    uvloop.run(main())
