from fbchat import Client, models
from otogi import Otogi
from admin import Admin
from bridget import BridgetFB
import json
import threading
import requests
import queue
import traceback
import pymongo
import enum
import inspect
import importlib
import sys

#==================================================================================================================================================

class FBThread:
    def __init__(self, *, thread_id=None, thread_type=None):
        self.thread_id = thread_id
        self.thread_type = thread_type

    def reply(self, text, **kwargs):
        return self.bot.send_message(self, text, **kwargs)

#==================================================================================================================================================

class FBMessage:
    def __init__(self, *, bot, content=None, mentions=None, emoji_size=None, sticker=None, attachments=None, reactions=None, author_id=None, thread_id=None, thread_type=None):
        self.bot = bot
        self.content = content
        self.text = content
        self.mentions = mentions or []
        self.emoji_size = emoji_size
        self.sticker = sticker
        self.attachments = attachments or []
        self.reactions = reactions or {}
        self.author_id = author_id
        self.thread_id = thread_id
        self.thread_type = thread_type
        self.raw_command = None

    def reply(self, text, **kwargs):
        return self.bot.send_message(self, text, **kwargs)

#==================================================================================================================================================

class ActionType(enum.Enum):
    NICKNAME_CHANGE = 1
    USERS_ADD = 2
    USER_REMOVE = 3

#==================================================================================================================================================

class FBAction:
    def __init__(self, *, bot, action_type, author_id, after, thread_id, thread_type):
        self.bot = bot
        self.action_type = action_type
        self.author_id = author_id
        self.after = after
        self.thread_id = thread_id
        self.thread_type = thread_type

    def reply(self, text, **kwargs):
        return self.bot.send_message(self, text, **kwargs)

#==================================================================================================================================================

class Bot(Client):
    def __init__(self, *args, initial_extensions=None, **kwargs):
        self.mongo_client = pymongo.MongoClient()
        self.db = self.mongo_client.belphydb
        self.initial_extensions = initial_extensions or []

        self.cogs = {}
        self.extensions = {}
        self.listeners = {}
        self.event_list = queue.Queue()
        self.DEFAULT_PREFIX = (">>", "!!")
        self.lock = threading.Lock()

        for item in dir(self):
            if item.startswith("on_"):
                ev = item[3:]
                if ev in self.listeners:
                    self.listeners[ev].append(getattr(self, item))
                else:
                    self.listeners[ev] = [getattr(self, item)]

        self.update_prefix()

        super().__init__(*args, **kwargs)

    def update_prefix(self):
        prefix_data = self.db.guild_data.find_one({"guild_id": 301713435635482624}, projection={"_id": -1, "prefixes": 1})
        self.prefixes = set(prefix_data.get("prefixes", []))
        self.prefixes.update(self.DEFAULT_PREFIX)

    def add_cog(self, cog):
        with self.lock:
            self.cogs[cog.__class__.__name__] = cog
            members = inspect.getmembers(cog)
            for name, member in members:
                if name.startswith("on_"):
                    ev = name[3:]
                    if ev in self.listeners:
                        self.listeners[ev].append(member)
                    else:
                        self.listeners[ev] = [member]

    def remove_cog(self, name):
        with self.lock:
            cog = self.cogs.pop(name, None)
            if cog is None:
                return
            for ev_name, listeners in self.listeners.items():
                for listener in listeners[:]:
                    if hasattr(listener, "__self__"):
                        if isinstance(cog, listener.__self__.__class__):
                            listeners.remove(listener)
            try:
                unloader = getattr(cog, f"_{cog.__class__.__name__}__unload")
            except AttributeError:
                pass
            else:
                unloader()
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

    def dispatch(self, event, *args):
        with self.lock:
            if event in self.listeners:
                lis = self.listeners[event]
                for l in lis:
                    self.create_task(l, *args)

    def create_task(self, f, *args, **kwargs):
        def safe_f(*args, **kwargs):
            try:
                f(*args, **kwargs)
            except:
                print(traceback.format_exc())
        thread = threading.Thread(target=safe_f, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()

    def send_message(self, target, text, **kwargs):
        if not isinstance(text, str):
            raise TypeError
        m = FBMessage(bot=self, content=text, **kwargs)
        self.send(m, target.thread_id, target.thread_type)
        return m

    def wait_for(self, event, *, check=None, timeout=None):
        params = queue.Queue()

        def wait_for_event(*args):
            try:
                c = check(*args)
            except:
                pass
            else:
                if c:
                    params.put(args)
        with self.lock:
            if event in self.listeners:
                self.listeners[event].append(wait_for_event)
            else:
                self.listeners[event] = [wait_for_event]
        try:
            fl = params.get(True, timeout)
        except TimeoutError:
            raise
        else:
            with self.lock:
                self.listeners[event].remove(wait_for_event)
            if len(fl) == 1:
                return fl[0]
            else:
                return fl

    def onMessage(self, *, mid, author_id, message_object, thread_id, thread_type, **kwargs):
        self.markAsDelivered(thread_id, message_object.uid)
        self.markAsRead(thread_id)
        if author_id != self.uid:
            message = FBMessage(
                bot=self, content=message_object.text, mentions=message_object.mentions, emoji_size=message_object.emoji_size,
                sticker=message_object.sticker, attachments=message_object.attachments, author_id=author_id, thread_id=thread_id, thread_type=thread_type
            )
            self.dispatch("message", message)

    def onNicknameChange(self, *, changed_for, new_nickname, thread_id, thread_type, **kwargs):
        action = FBAction(bot=self, action_type=ActionType.NICKNAME_CHANGE, author_id=changed_for, after=new_nickname, thread_id=thread_id, thread_type=thread_type)
        self.dispatch("nickname_change", action)

    def onPeopleAdded(self, *, added_ids, author_id, thread_id, **kwargs):
        action = FBAction(bot=self, action_type=ActionType.USERS_ADD, author_id=author_id, after=added_ids, thread_id=thread_id, thread_type=models.ThreadType.GROUP)
        self.dispatch("users_add", action)

    def onPersonRemoved(self, *, removed_id, author_id, thread_id, **kwargs):
        action = FBAction(bot=self, action_type=ActionType.USER_REMOVE, author_id=author_id, after=removed_id, thread_id=thread_id, thread_type=models.ThreadType.GROUP)
        self.dispatch("user_remove", action)

    def onMarkedSeen(self, *args, **kwargs):
        pass

    def onMessageDelivered(self, *args, **kwargs):
        pass

    def onMessageSeen(self, *args, **kwargs):
        pass

    def onInbox(self, *args, **kwargs):
        pass

    def onUnknownMesssageType(self, *, msg):
        self.dispatch("unknown_message", msg)

    def get_prefixes(self):
        return list(self.prefixes)

    def startListening(self):
        for extension in self.initial_extensions:
            self.load_extension(extension)
        super().startListening()
