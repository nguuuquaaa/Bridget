import flat
import traceback
from contextlib import redirect_stdout
import importlib
from io import StringIO
import textwrap

#==================================================================================================================================================

class Admin:
    def __init__(self, bot):
        self.bot = bot
        self.guild_data = bot.db.guild_data

    async def on_message(self, message):
        if message.author.id == "100000168277666":
            text = message.text
            if text:
                prefixes = self.bot.get_prefixes()
                for p in prefixes:
                    if text.startswith(p):
                        command = text[len(p):]
                        break
                else:
                    return
                if command.startswith(("eval")):
                    data = command[5:]
                    await self.cmd_eval(message, data)
                elif command.startswith(("updateprefix")):
                    await self.cmd_update_prefix(message)
                elif command.startswith(("reload ")):
                    data = command[7:]
                    await self.cmd_reload(message, data)
                elif command.startswith(("unload ")):
                    data = command[7:]
                    await self.cmd_unload(message, data)

    async def cmd_eval(self, message, data):
        data = data.strip()
        if data.startswith("```"):
            data = data.partition("\n")[2]
        code = data.strip("` \n")
        code = f"async def func():\n{textwrap.indent(data, '    ')}"
        env = {
            "bot": self.bot,
            "flat": flat,
            "message": message
        }
        try:
            exec(code, env)
        except Exception as e:
            return await message.thread.send(f"```py\n{e}```")
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
                await message.thread.send(f'```\n{value}{add_text}```')

    async def cmd_update_prefix(self, message):
        await self.bot.update_prefixes()

    async def cmd_reload(self, message, extension):
        try:
            self.bot.unload_extension(extension)
            self.bot.load_extension(extension)
        except Exception as e:
            await message.thread.send(f"Failed {extension}:\n{traceback.format_exc(1)}")
        else:
            await message.thread.send("Done")

    async def cmd_unload(self, message, extension):
        if extension in self.bot.extensions:
            self.bot.unload_extension(extension)
            await message.thread.send("Done")
        else:
            await message.thread.send("Extension doesn't exist.")

#==================================================================================================================================================
def setup(bot):
    bot.add_cog(Admin(bot))
