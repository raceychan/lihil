from lihil import Lihil, Route, Text

# all_users = Route("/user")
# user = all_users / "{user_id}"

root = Route()


@root.get
async def homepage() -> Text:
    return ""


@root.sub("/user").post
async def userinfo() -> Text:
    return ""


@root.sub("/user/{user_id}").get
async def get_user(user_id: str) -> Text:
    return user_id


lhl = Lihil[None](routes=[root])


if __name__ == "__main__":
    lhl.run(__file__)
