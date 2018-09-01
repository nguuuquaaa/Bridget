import flat
import traceback
from motor import motor_asyncio
import inspect
import importlib
import sys

#==================================================================================================================================================

class Bot(flat.Client):
    def __init__(self, *args, initial_extensions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.mongo_client = motor_asyncio.AsyncIOMotorClient()
        self.db = self.mongo_client.belphydb

        self.cogs = {}
        self.extensions = {}
        self.DEFAULT_PREFIX = (">>", "!!")
        if initial_extensions:
            for e in initial_extensions:
                self.load_extension(e)

        self.loop.create_task(self.update_prefixes())

    async def update_prefixes(self):
        prefix_data = await self.db.guild_data.find_one({"guild_id": 301713435635482624}, projection={"_id": -1, "prefixes": 1})
        self.prefixes = prefix_data.get("prefixes") or self.DEFAULT_PREFIX
        self.prefixes.sort(reverse=True)

    def get_prefixes(self):
        return self.prefixes

    def add_cog(self, cog):
        self.cogs[cog.__class__.__name__] = cog
        members = inspect.getmembers(cog)
        for name, member in members:
            if name.startswith("on_"):
                ev = name[3:]
                if ev in self._form_events:
                    self._form_events[ev].append(member)
                else:
                    self._form_events[ev] = [member]

    def remove_cog(self, name):
        cog = self.cogs.pop(name, None)
        if cog is None:
            return
        for name, events in self._form_events.items():
            for ev in events[:]:
                if hasattr(ev, "__self__"):
                    if isinstance(cog, ev.__self__.__class__):
                        listeners.remove(ev)
        try:
            unloader = getattr(cog, f"_{cog.__class__.__name__}__unload")
        except AttributeError:
            pass
        else:
            unloader()
        finally:
            del cog

    #shameless copy from discord.py
    def load_extension(self, name):
        if name in self.extensions:
            return

        lib = importlib.import_module(name)
        if not hasattr(lib, "setup"):
            del lib
            del sys.modules[name]
            raise AttributeError("Extension does not have a setup function")

        lib.setup(self)
        self.extensions[name] = lib

    def _is_submodule(self, parent, child):
        return parent == child or child.startswith(parent + ".")

    def unload_extension(self, name):
        lib = self.extensions.get(name)
        if lib is None:
            return

        lib_name = lib.__name__
        for cogname, cog in self.cogs.copy().items():
            if self._is_submodule(lib_name, cog.__module__):
                self.remove_cog(cogname)

        try:
            func = getattr(lib, "teardown")
        except AttributeError:
            pass
        else:
            try:
                func(self)
            except:
                pass
        finally:
            del lib
            del self.extensions[name]
            del sys.modules[name]
            for module in list(sys.modules.keys()):
                if self._is_submodule(lib_name, module):
                    del sys.modules[module]
    #end shameless copy
