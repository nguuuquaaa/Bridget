import traceback
from fbchat import models
from contextlib import redirect_stdout
import importlib
from io import StringIO
import textwrap

#==================================================================================================================================================

class Admin:
    def __init__(self, bot):
        self.bot = bot
        self.guild_data = bot.db.guild_data

    def on_message(self, message):
        if message.author_id == "100000168277666":
            content = message.content
            if content:
                prefixes = self.bot.get_prefixes()
                for p in prefixes:
                    if content.startswith(p):
                        command = content[len(p):]
                        break
                else:
                    return
                if command.startswith(("eval")):
                    data = command[5:]
                    self.cmd_eval(message, data)
                elif command.startswith(("updateprefix")):
                    self.cmd_update_prefix(message)
                elif command.startswith(("reload ")):
                    data = command[7:]
                    self.cmd_reload(message, data)
                elif command.startswith(("unload ")):
                    data = command[7:]
                    self.cmd_unload(message, data)

    def cmd_eval(self, message, data):
        data = data.strip()
        if data.startswith("```"):
            data = data.partition("\n")[2]
        code = data.strip("` \n")
        env = {
            "bot": self.bot,
            "models": models,
            "message": message
        }
        env.update(locals())
        stdout = StringIO()
        try:
            with redirect_stdout(stdout):
                exec(code, env)
        except:
            add_text = f"\n{traceback.format_exc()}"
        else:
            add_text = ""
        finally:
            value = stdout.getvalue().strip()
            if value or add_text:
                message.reply(f"```\n{value}{add_text}\n```")

    def cmd_update_prefix(self, message):
        self.bot.update_prefix()

    def cmd_reload(self, message, extension):
        try:
            self.bot.unload_extension(extension)
            self.bot.load_extension(extension)
            message.reply("Done")
        except Exception as e:
            message.reply(f"Failed {extension}:\n{traceback.format_exc(1)}")

    def cmd_unload(self, message, extension):
        if extension in self.bot.extensions:
            self.bot.unload_extension(extension)
            message.reply("Done")

#==================================================================================================================================================
def setup(bot):
    bot.add_cog(Admin(bot))
