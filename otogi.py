import flat
import re

#==================================================================================================================================================

class Daemon:
    def __init__(self, data):
        for key, value in data.items():
            if key[0] != "_":
                setattr(self, key, value)

    def text_form(self):
        sab = ""
        if self.skills:
            sab = f"{sab}\n*Skill*\n"
            for d in self.skills:
                sab = f"{sab}------------------------\n\U0001f539{d['name']}\n\u25aa{d['effect']}\n"
        if self.abilities:
            sab = f"{sab}==============\n*Ability*\n"
            for d in self.abilities:
                sab = f"{sab}------------------------\n\U0001f539{d['name']}\n\u25aa{d['effect']}\n"
        if self.bonds:
            sab = f"{sab}==============\n*Bond*\n"
            for d in self.bonds:
                sab = f"{sab}------------------------\n\U0001f539{d['name']}\n\u25aa{d['effect']}\n"
        pic_url = self.true_url
        star = '\u2b50'
        text_body = \
            f"*{self.name.upper()}*\n" \
            f"{self.rarity*star}\n" \
            f"*Type*: {self.daemon_type.capitalize()}\n" \
            f"*Class*: {self.daemon_class.capitalize()}\n" \
            f"*ATK*: {self.atk}\n" \
            f"*HP*: {self.hp}\n" \
            f"{sab}"
        return pic_url, text_body

    def more_info(self):
        des = self.description.partition(".")
        va = self.voice_actor
        illu = self.illustrator
        how = self.how_to_acquire
        trv = self.notes_and_trivia
        quotes = self.quotes
        pic_url = self.true_artwork
        text_body = \
            f"*{self.name.upper()}*\n" \
            f"_{des[0]}._{des[2]}\n" \
            f"*Voice Actor*\n{va if va else '--'}\n" \
            f"==============\n*Illustrator*\n{illu if illu else '--'}\n" \
            f"==============\n*How to Acquire*\n{how if how else '--'}\n" \
            f"==============\n*Notes & Trivia*\n{trv if trv else '--'}\n" \
            "==============\n*Quotes*\n" \
            f"\u25aaMain: {quotes['main']['value']}\n" \
            f"\u25aaSkill: {quotes['skill']['value']}\n" \
            f"\u25aaSummon: {quotes['summon']['value']}\n" \
            f"\u25aaLimit break: {quotes['limit_break']['value']}"
        return pic_url, text_body

    @property
    def atk(self):
        if self.mlb_atk:
            return f"{self.max_atk}/{self.mlb_atk}"
        else:
            return self.max_atk

    @property
    def hp(self):
        if self.mlb_hp:
            return f"{self.max_hp}/{self.mlb_hp}"
        else:
            return self.max_hp

    @property
    def true_artwork(self):
        if self.artwork_url:
            return self.artwork_url
        else:
            return "https://i.imgur.com/62di8EB.jpg"

    @property
    def true_url(self):
        if self.pic_url:
            return self.pic_url
        else:
            return "https://i.imgur.com/62di8EB.jpg"

#==================================================================================================================================================

class Otogi:
    def __init__(self, bot):
        self.bot = bot
        self.daemon_collection = bot.db.daemon_collection
        self.guild_data = bot.db.guild_data

    async def search(self, name):
        atts = ("name", "alias")
        try:
            item_id = int(name)
        except:
            pass
        else:
            result = await self.daemon_collection.find_one({"id": item_id})
            if result:
                return [Daemon(result)]
            else:
                return []
        name = name.lower()
        regex = ".*?".join(map(re.escape, name.split()))
        daemons = []
        async for daemon_data in self.daemon_collection.find({
            "$or": [
                {
                    att: {
                        "$regex": regex,
                        "$options": "i"
                    }
                } for att in atts
            ]
        }):
            d = Daemon(daemon_data)
            daemons.append(d)
        return daemons

    async def on_message(self, message):
        text = message.text
        if text:
            prefixes = self.bot.get_prefixes()
            for p in prefixes:
                if text.startswith(p):
                    command = text[len(p):]
                    break
            else:
                return
            if command.startswith(("d ", "daemon ")):
                if command.startswith("d "):
                    name = command[2:]
                else:
                    name = command[7:]
                await self.cmd_daemon(message, name.strip())

            elif command.startswith(("t ", "trivia ")):
                if command.startswith("t "):
                    name = command[2:]
                else:
                    name = command[7:]
                await self.cmd_trivia(message, name.strip())

    async def cmd_daemon(self, message, name):
        daemons = await self.search(name)
        if not daemons:
            return await message.thread.send(f"Can't find {name} in database.")
        elif len(daemons) == 1:
            index = 0
        else:
            all_names = "\n".join([f"{i+1}. {d.name}" for i, d in enumerate(daemons)])
            if len(all_names) >= 1000:
                return await message.thread.send("Too many results.")
            await message.thread.send(f"Do you mean:\n{all_names}")
            try:
                msg = await self.bot.wait_for("message", check=lambda m: m.author.id==message.author.id, timeout=60)
            except TimeoutError:
                return
            else:
                try:
                    index = int(msg.text) - 1
                except ValueError:
                    return
        try:
            d = daemons[index]
        except IndexError:
            return
        else:
            try:
                pic_url, text_body = d.text_form()
            except:
                await message.thread.send(f"{d.name}'s info is incompleted.")
            else:
                if pic_url:
                    await message.thread.send(flat.Content().embed_link(pic_url, append=False))
                await message.thread.send(text_body)

    async def cmd_trivia(self, message, name):
        daemons = self.search(name)
        if not daemons:
            return await message.thread.send(f"Can't find {name} in database.")
        elif len(daemons) == 1:
            index = 0
        else:
            all_names = "\n".join([f"{i+1}. {d.name}" for i, d in enumerate(daemons)])
            if len(all_names) >= 1000:
                return await message.thread.send("Too many results.")
            await message.thread.send(f"Do you mean:\n{all_names}")
            try:
                msg = await self.bot.wait_for("message", check=lambda m: m.author.id==message.author.id, timeout=60)
            except TimeoutError:
                return
            else:
                try:
                    index = int(msg.text) - 1
                except ValueError:
                    return
        try:
            d = daemons[index]
        except IndexError:
            return
        else:
            try:
                pic_url, text_body = d.more_info()
            except:
                await message.thread.send(f"{d.name}'s info is incompleted.")
            else:
                if pic_url:
                    await message.thread.send(flat.Content().embed_link(pic_url, append=False))
                await message.thread.send(text_body)

#==================================================================================================================================================
def setup(bot):
    bot.add_cog(Otogi(bot))
