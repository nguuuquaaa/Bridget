import discord
from discord.ext import commands
import flat
import re
import threading
from motor import motor_asyncio
from contextlib import redirect_stdout
import traceback
from io import StringIO, BytesIO
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

discord_messages = asyncio.Queue()
fb_messages = asyncio.Queue()

def try_it(func):
    async def new_func(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except:
            traceback.print_exc()

    return new_func

#==================================================================================================================================================

class BridgetDiscord(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mongo_client = motor_asyncio.AsyncIOMotorClient()
        self.db = self.mongo_client.belphydb

    async def on_message(self, message):
        if not message.author.bot:
            await self.process_commands(message)

#==================================================================================================================================================

class DoStuff:
    def __init__(self, bot):
        self.bot = bot
        self.post_to_discord = bot.loop.create_task(self.wait_for_fb_messages())
        self.config = bot.db.belphegor_config

    def __unload(self):
        self.post_to_discord.cancel()

    async def on_ready(self):
        print("Logged in as")
        print(self.bot.user.name)
        print(self.bot.user.id)
        print("------")
        await asyncio.sleep(1)
        await self.bot.change_presence(activity=discord.Activity(name="\U0001f440", type=discord.ActivityType.watching))

    async def on_message(self, message):
        if message.author.id == 435017405220126720:
            return
        if message.channel.id == 435017382809960448:
            await discord_messages.put(message)

    async def do_stuff_after(self, coro, after):
        await asyncio.sleep(after)
        await coro

    @try_it
    async def wait_for_fb_messages(self):
        self.fb_users = (await self.config.find_one({"category": "fb_users"}, projection={"_id": False, "category": False}))["data"]
        await self.bot.wait_until_ready()
        ch = self.bot.get_channel(435017382809960448)
        wh = (await ch.webhooks())[0]
        self.wh = wh
        loop = self.bot.loop

        while True:
            message = await fb_messages.get()
            author = message.author
            user = get_element(self.fb_users, lambda x: x["facebook_id"]==author.id, {})
            if len(author.name) > 25:
                name = f"(FB) {author.name[:22]}..."
            else:
                name = f"(FB) {author.name}"
            avatar_url = user.get("avatar_url")
            if not avatar_url:
                u = self.bot.get_user(user.get("discord_id"))
                if u:
                    avatar_url = u.avatar_url

            async def exe(*args, **kwargs):
                try:
                    await wh.execute(*args, username=name, avatar_url=avatar_url, **kwargs)
                except:
                    traceback.print_exc()
                    loop.create_task(self.do_stuff_after(wh.execute(*args, username=name, avatar_url=avatar_url, **kwargs), 10))

            if message.text:
                await exe(convert_to_discord(message.text))

            if message.sticker:
                b = BytesIO()
                await message.sticker.to_gif(b)
                await exe(file=discord.File(b.getvalue(), f"sticker_{message.sticker.id}.gif"))

            if message.files:
                content = []
                for f in message.files:
                    url = None
                    for i in range(3):
                        try:
                            url = await f.get_url()
                        except:
                            continue
                        else:
                            break
                    if url:
                        content.append(url)
                await exe("\n".join(content))

    @commands.command(name="eval")
    @commands.check(lambda ctx: ctx.author.id==247360205086654464)
    async def _eval(self, ctx, *, data: str):
        data = data.strip()
        if data.startswith("```"):
            data = data.splitlines()[1:]
        else:
            data = data.splitlines()
        data = "\n    ".join(data).strip("` \n")
        code = f"async def func():\n    {data}"
        env = {
            "bot": self.bot,
            "ctx": ctx,
            "discord": discord,
            "commands": commands
        }
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

    @commands.command()
    @commands.check(lambda ctx: ctx.author.id==247360205086654464)
    async def setuser(self, ctx, facebook_id, member: discord.Member=None):
        user = get_element(self.bot.fb_users, lambda x: x["user_id"]==user_id)
        new_user = {
            "facebook_id": facebook_id,
            "discord_id": getattr(member, "id", None),
            "avatar_url": None
        }
        self.bot.fb_users.append(new_user)
        await self.bot.config.update_one({"category": "fb_users"}, {"$addToSet": {"data": new_user}})
        await ctx.message.add_reaction("\u2705")

    @commands.command()
    @commands.check(lambda ctx: get_element(ctx.bot.fb_users, lambda x: x["discord_id"]==ctx.author.id))
    async def setavatar(ctx, *, avatar_url=None):
        if not avatar_url:
            avatar_url = None
        if avatar_url.startswith(("http://", "https://")):
            item = get_element(self.bot.fb_users, lambda x: x["discord_id"]==ctx.author.id)
            item["avatar_url"] = avatar_url
            await self.bot.config.update_one({"category": "fb_users", "data.facebook_id": item["facebook_id"]}, {"$set": {"data.$.avatar_url": avatar_url}})
            await ctx.message.add_reaction("\u2705")
        else:
            await ctx.message.add_reaction("\u274c")

    @commands.command()
    @commands.check(lambda ctx: ctx.author.id==247360205086654464)
    async def force(ctx, facebook_id, field, value=None):
        item = get_element(self.bot.fb_users, lambda x: x["facebook_id"]==facebook_id, {})
        if field in item:
            item[field] = value
            await self.bot.config.update_one({"category": "fb_users", "data.facebook_id": facebook_id}, {"$set": {f"data.$.{field}": value}})
            await ctx.message.add_reaction("\u2705")
        else:
            await ctx.message.add_reaction("\u274c")

#==================================================================================================================================================

class BridgetFB:
    def __init__(self, bot):
        self.bot = bot
        self.last_author = None
        self.discord_to_facebook = self.bot.loop.create_task(self.wait_for_discord_messages())

    async def on_message(self, message):
        if message.thread.id == "1240696179284814":
            if message.author.id == self.bot.user.id:
                return
            else:
                self.last_author = message.author.id
            await fb_messages.put(message)

    @try_it
    async def wait_for_discord_messages(self):
        if not self.bot._ready.is_set():
            await self.bot._ready.wait()
        thread = await self.bot._state.get_thread("1240696179284814")

        while True:
            message = await discord_messages.get()
            sendable = False

            author = message.author
            if author.bot:
                author_str = f"{author.display_name}\u1d2e\u1d3c\u1d40"
            else:
                author_str = author.display_name

            ctn = flat.Content()

            if message.content:
                text = convert_to_fb(message.content)
                sendable = True
            else:
                text = ""

            if message.attachments:
                sendable = True
                for a in message.attachments:
                    ctn.embed(a.url, append=False)

            if sendable:
                if message.author.id != self.last_author:
                    self.last_author = message.author.id
                    if text:
                        ctn.write(f"```\n(Discord) {author_str}\n```\n{text}")
                else:
                    if text:
                        ctn.write(text)
                await thread.send(ctn)

#==================================================================================================================================================

def setup(bot):
    bot.add_cog(BridgetFB(bot))

    bridget_discord = BridgetDiscord(command_prefix="//", loop=bot.loop)
    bridget_discord.add_cog(DoStuff(bridget_discord))
    bot.loop.create_task(bridget_discord.start(credentials.discord_token))

    async def close():
        await bot.close()
        await bridget_discord.close()

    bot.close = close
