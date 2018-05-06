import discord
from discord.ext import commands
import re
from fbchat import models
import multiprocessing
import threading
from motor import motor_asyncio
from contextlib import redirect_stdout
import traceback
from io import StringIO
import time
import queue
import asyncio
import weakref
import credentials

_discord_format = re.compile("\<\:\w+:[0-9]{18}\>")
_discord_to_fb = {"<:ahihi:301721953394229258>": ":)", "<:dm:301730374743097346>": "\U0001f621"}
_fb_format = re.compile("\:\)|\U0001f621")
_fb_to_discord = {value: key for key, value in _discord_to_fb.items()}

def convert_to_fb(text):
    return _discord_format.sub(lambda m: _discord_to_fb.get(m.group(0), ""), text)

def convert_to_discord(text):
    return _fb_format.sub(lambda m: _fb_to_discord.get(m.group(0), ""), text)

def get_element(container, pred, default=None):
    for item in container:
        try:
            if pred(item):
                return item
        except:
            pass
    else:
        return default

discord_messages = multiprocessing.Queue()
fb_messages = multiprocessing.Queue()

#==================================================================================================================================================

class BridgetDiscord(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mongo_client = motor_asyncio.AsyncIOMotorClient()
        self.db = self.mongo_client.belphydb
        self.config = self.db.belphegor_config
        self.post_to_discord = weakref.ref(self.loop.create_task(self.wait_for_fb_messages()))

    async def on_message(self, message):
        if message.author.id == 435017405220126720:
            return
        if message.channel.id == 435017382809960448:
            if message.author.bot:
                name = f"{message.author.display_name}\u1d2e\u1d3c\u1d40"
            else:
                name = message.author.display_name
            if message.content:
                content = convert_to_fb(message.content)
                discord_messages.put((name, content))
            if message.attachments:
                for a in message.attachments:
                    discord_messages.put((name, a.url))
        if not message.author.bot:
            await self.process_commands(message)

    async def wait_for_fb_messages(self):
        self.fb_users = (await self.config.find_one({"category": "fb_users"}, projection={"_id": False, "category": False}))["data"]
        await self.wait_until_ready()
        ch = self.get_channel(435017382809960448)
        wh = (await ch.webhooks())[0]
        self.wh = wh

        while True:
            try:
                author_id, nickname, content = await self.loop.run_in_executor(None, fb_messages.get, True, 5)
            except queue.Empty:
                continue
            user = get_element(self.fb_users, lambda x: x["facebook_id"]==author_id, {})
            if len(nickname) > 25:
                nickname = f"{nickname[:22]}..."
            avatar_url = user.get("avatar_url")
            if not avatar_url:
                u = self.get_user(user.get("discord_id"))
                if u:
                    avatar_url = u.avatar_url
            await wh.execute(content, username=f"(FB) {nickname}", avatar_url=avatar_url)

    async def close(self):
        self.post_to_discord().cancel()
        await super().close()
        await asyncio.sleep(6)

#==================================================================================================================================================

bridget = BridgetDiscord(command_prefix="//")

@bridget.event
async def on_ready():
    print("Logged in as")
    print(bridget.user.name)
    print(bridget.user.id)
    print("------")
    await asyncio.sleep(1)
    await bridget.change_presence(activity=discord.Game(name="\U0001f440"))

@bridget.command(name="eval")
@commands.check(lambda ctx: ctx.author.id==247360205086654464)
async def _eval(ctx, *, data: str):
    data = data.strip()
    if data.startswith("```"):
        data = data.splitlines()[1:]
    else:
        data = data.splitlines()
    data = "\n    ".join(data).strip("` \n")
    code = f"async def func():\n    {data}"
    env = {
        "bot": bridget,
        "ctx": ctx,
        "discord": discord,
        "commands": commands
    }
    env.update(locals())
    try:
        exec(code, env)
    except Exception as e:
        return await ctx.send(f"```py\n{e}\n```")
    stdout = StringIO()
    func = env["func"]
    try:
        with redirect_stdout(stdout):
            await func()
    except:
        add_text = f"\n{traceback.format_exc()}"
    else:
        add_text = ""
    finally:
        value = stdout.getvalue()
        if value or add_text:
            await ctx.send(f'```\n{value}{add_text}\n```')

@bridget.command()
@commands.check(lambda ctx: ctx.author.id==247360205086654464)
async def setuser(ctx, facebook_id, member: discord.Member=None):
    user = get_element(bridget.fb_users, lambda x: x["user_id"]==user_id)
    new_user = {
        "facebook_id": facebook_id,
        "discord_id": getattr(member, "id", None),
        "avatar_url": None
    }
    bridget.fb_users.append(new_user)
    await bridget.config.update_one({"category": "fb_users"}, {"$addToSet": {"data": new_user}})
    await ctx.message.add_reaction("\u2705")

@bridget.command()
@commands.check(lambda ctx: get_element(bridget.fb_users, lambda x: x["discord_id"]==ctx.author.id))
async def setavatar(ctx, *, avatar_url=None):
    if not avatar_url:
        avatar_url = None
    if avatar_url.startswith(("http://", "https://")):
        item = get_element(bridget.fb_users, lambda x: x["discord_id"]==ctx.author.id)
        item["avatar_url"] = avatar_url
        await bridget.config.update_one({"category": "fb_users", "data.facebook_id": item["facebook_id"]}, {"$set": {"data.$.avatar_url": avatar_url}})
        await ctx.message.add_reaction("\u2705")
    else:
        await ctx.message.add_reaction("\u274c")

@bridget.command()
@commands.check(lambda ctx: ctx.author.id==247360205086654464)
async def force(ctx, facebook_id, field, value=None):
    item = get_element(bridget.fb_users, lambda x: x["facebook_id"]==facebook_id, {})
    if field in item:
        item[field] = value
        await bridget.config.update_one({"category": "fb_users", "data.facebook_id": facebook_id}, {"$set": {f"data.$.{field}": value}})
        await ctx.message.add_reaction("\u2705")
    else:
        await ctx.message.add_reaction("\u274c")

#==================================================================================================================================================

class BridgetFB:
    def __init__(self, bot):
        self.bot = bot
        bot.create_task(self.wait_for_discord_messages)
        self.last_author = None
        self._running = True

    def __unload(self):
        process.terminate()
        self._running = False

    def on_message(self, message):
        if message.thread_id == "1240696179284814":
            if message.content:
                self.last_author = message.author_id
                content = convert_to_discord(message.content)
                nickname = self.nicknames.get(message.author_id)
                if not nickname:
                    user = self.users.get(message.author_id)
                    if user:
                        nickname = f"{user.last_name or ''} {user.first_name or ''}".strip()
                    else:
                        nickname = message.author_id
                fb_messages.put((message.author_id, nickname, content))

    def on_raw_message(self, raw_message):
        metadata = raw_message["messageMetadata"]
        thread_id = next(iter(metadata["threadKey"].values()))
        if thread_id == "1240696179284814":

            author_id = metadata["actorFbId"]
            if author_id == self.bot.uid:
                return
            nickname = self.nicknames.get(author_id)
            if not nickname:
                user = self.users.get(author_id)
                if user:
                    nickname = f"{user.last_name or ''} {user.first_name or ''}".strip()
                else:
                    nickname = author_id

            if raw_message.get("attachments"):
                data_map = raw_message.get("genericDataMap")
                if data_map:
                    url = data_map["data"]["e"]["asMap"]["data"]["serializedFields"]["asMap"]["external_url"]["asString"]
                    fb_messages.put((author_id, nickname, url))
                else:
                    for attachment in raw_message["attachments"]:
                        a = attachment["mercury"].get("blob_attachment")
                        if a:
                            url = a.get("large_preview")["uri"]
                            fb_messages.put((author_id, nickname, url))

    def on_nickname_change(self, action):
        self.nicknames[action.author_id] = action.after

    def on_users_add(self, action):
        user = self.bot.fetchUserInfo(action.author_id)
        self.users.update(user)

    def on_user_remove(self, action):
        self.nicknames.pop(action.author_id, None)
        self.users.pop(action.author_id, None)

    def wait_for_discord_messages(self):
        while not self.bot.listening:
            time.sleep(0.1)
        group_info = self.bot.fetchGroupInfo("1240696179284814")["1240696179284814"]
        group_info.thread_id = group_info.uid
        group_info.thread_type = group_info.type
        self.nicknames = group_info.nicknames
        self.users = self.bot.fetchUserInfo(*group_info.participants)
        while self._running:
            try:
                author, content = discord_messages.get(True, 5)
            except queue.Empty:
                continue
            if author != self.last_author:
                self.last_author = author
                self.bot.send_message(group_info, f"```\n(Discord) {author}\n```\n{content}")
            else:
                self.bot.send_message(group_info, content)

#==================================================================================================================================================

def setup(bot):
    process = multiprocessing.Process(target=bridget.run, args=(credentials.discord_token,), daemon=True)
    process.start()
    bot.add_cog(BridgetFB(bot))
