import fbchat
from fbchat.models import *
from fbchat.utils import *
from fbchat.graphql import *

#==================================================================================================================================================

def _parseMessage(self, content):
    if 'ms' not in content: return

    for m in content["ms"]:
        mtype = m.get("type")
        try:
            # Things that directly change chat
            if mtype == "delta":

                def getThreadIdAndThreadType(msg_metadata):
                    """Returns a tuple consisting of thread ID and thread type"""
                    id_thread = None
                    type_thread = None
                    if 'threadFbId' in msg_metadata['threadKey']:
                        id_thread = str(msg_metadata['threadKey']['threadFbId'])
                        type_thread = ThreadType.GROUP
                    elif 'otherUserFbId' in msg_metadata['threadKey']:
                        id_thread = str(msg_metadata['threadKey']['otherUserFbId'])
                        type_thread = ThreadType.USER
                    return id_thread, type_thread

                delta = m["delta"]
                delta_type = delta.get("type")
                metadata = delta.get("messageMetadata")

                if metadata:
                    mid = metadata["messageId"]
                    author_id = str(metadata['actorFbId'])
                    ts = int(metadata.get("timestamp"))

                # Added participants
                if 'addedParticipants' in delta:
                    added_ids = [str(x['userFbId']) for x in delta['addedParticipants']]
                    thread_id = str(metadata['threadKey']['threadFbId'])
                    self.onPeopleAdded(mid=mid, added_ids=added_ids, author_id=author_id, thread_id=thread_id,
                                       ts=ts, msg=m)

                # Left/removed participants
                elif 'leftParticipantFbId' in delta:
                    removed_id = str(delta['leftParticipantFbId'])
                    thread_id = str(metadata['threadKey']['threadFbId'])
                    self.onPersonRemoved(mid=mid, removed_id=removed_id, author_id=author_id, thread_id=thread_id,
                                         ts=ts, msg=m)

                # Color change
                elif delta_type == "change_thread_theme":
                    new_color = graphql_color_to_enum(delta["untypedData"]["theme_color"])
                    thread_id, thread_type = getThreadIdAndThreadType(metadata)
                    self.onColorChange(mid=mid, author_id=author_id, new_color=new_color, thread_id=thread_id,
                                       thread_type=thread_type, ts=ts, metadata=metadata, msg=m)

                # Emoji change
                elif delta_type == "change_thread_icon":
                    new_emoji = delta["untypedData"]["thread_icon"]
                    thread_id, thread_type = getThreadIdAndThreadType(metadata)
                    self.onEmojiChange(mid=mid, author_id=author_id, new_emoji=new_emoji, thread_id=thread_id,
                                       thread_type=thread_type, ts=ts, metadata=metadata, msg=m)

                # Thread title change
                elif delta.get("class") == "ThreadName":
                    new_title = delta["name"]
                    thread_id, thread_type = getThreadIdAndThreadType(metadata)
                    self.onTitleChange(mid=mid, author_id=author_id, new_title=new_title, thread_id=thread_id,
                                       thread_type=thread_type, ts=ts, metadata=metadata, msg=m)

                # Nickname change
                elif delta_type == "change_thread_nickname":
                    changed_for = str(delta["untypedData"]["participant_id"])
                    new_nickname = delta["untypedData"]["nickname"]
                    thread_id, thread_type = getThreadIdAndThreadType(metadata)
                    self.onNicknameChange(mid=mid, author_id=author_id, changed_for=changed_for,
                                          new_nickname=new_nickname,
                                          thread_id=thread_id, thread_type=thread_type, ts=ts, metadata=metadata, msg=m)

                # Message delivered
                elif delta.get("class") == "DeliveryReceipt":
                    message_ids = delta["messageIds"]
                    delivered_for = str(delta.get("actorFbId") or delta["threadKey"]["otherUserFbId"])
                    ts = int(delta["deliveredWatermarkTimestampMs"])
                    thread_id, thread_type = getThreadIdAndThreadType(delta)
                    self.onMessageDelivered(msg_ids=message_ids, delivered_for=delivered_for,
                                            thread_id=thread_id, thread_type=thread_type, ts=ts, metadata=metadata, msg=m)

                # Message seen
                elif delta.get("class") == "ReadReceipt":
                    seen_by = str(delta.get("actorFbId") or delta["threadKey"]["otherUserFbId"])
                    seen_ts = int(delta["actionTimestampMs"])
                    delivered_ts = int(delta["watermarkTimestampMs"])
                    thread_id, thread_type = getThreadIdAndThreadType(delta)
                    self.onMessageSeen(seen_by=seen_by, thread_id=thread_id, thread_type=thread_type,
                                       seen_ts=seen_ts, ts=delivered_ts, metadata=metadata, msg=m)

                # Messages marked as seen
                elif delta.get("class") == "MarkRead":
                    seen_ts = int(delta.get("actionTimestampMs") or delta.get("actionTimestamp"))
                    delivered_ts = int(delta.get("watermarkTimestampMs") or delta.get("watermarkTimestamp"))

                    threads = []
                    if "folders" not in delta:
                        threads = [getThreadIdAndThreadType({"threadKey": thr}) for thr in delta.get("threadKeys")]

                    # thread_id, thread_type = getThreadIdAndThreadType(delta)
                    self.onMarkedSeen(threads=threads, seen_ts=seen_ts, ts=delivered_ts, metadata=delta, msg=m)

                # New message
                elif delta.get("class") == "NewMessage":
                    self.dispatch("raw_message", delta)
                    mentions = []
                    if delta.get('data') and delta['data'].get('prng'):
                        try:
                            mentions = [Mention(str(mention.get('i')), offset=mention.get('o'), length=mention.get('l')) for mention in parse_json(delta['data']['prng'])]
                        except Exception:
                            log.exception('An exception occured while reading attachments')

                    sticker = None
                    attachments = []
                    if delta.get('attachments'):
                        try:
                            for a in delta['attachments']:
                                mercury = a['mercury']
                                if mercury.get('blob_attachment'):
                                    image_metadata = a.get('imageMetadata', {})
                                    attach_type = mercury['blob_attachment']['__typename']
                                    attachment = graphql_to_attachment(mercury.get('blob_attachment', {}))

                                    if attach_type == ['MessageFile', 'MessageVideo', 'MessageAudio']:
                                        # TODO: Add more data here for audio files
                                        attachment.size = int(a['fileSize'])
                                    attachments.append(attachment)
                                elif mercury.get('sticker_attachment'):
                                    sticker = graphql_to_sticker(a['mercury']['sticker_attachment'])
                                elif mercury.get('extensible_attachment'):
                                    # TODO: Add more data here for shared stuff (URLs, events and so on)
                                    pass
                        except Exception:
                            log.exception('An exception occured while reading attachments: {}'.format(delta['attachments']))

                    if metadata and metadata.get('tags'):
                        emoji_size = get_emojisize_from_tags(metadata.get('tags'))

                    message = Message(
                        text=delta.get('body'),
                        mentions=mentions,
                        emoji_size=emoji_size,
                        sticker=sticker,
                        attachments=attachments
                    )
                    message.uid = mid
                    message.author = author_id
                    message.timestamp = ts
                    #message.reactions = {}
                    thread_id, thread_type = getThreadIdAndThreadType(metadata)
                    self.onMessage(mid=mid, author_id=author_id, message=delta.get('body', ''), message_object=message,
                                   thread_id=thread_id, thread_type=thread_type, ts=ts, metadata=metadata, msg=m)

                # Unknown message type
                else:
                    self.onUnknownMesssageType(msg=m)

            # Inbox
            elif mtype == "inbox":
                self.onInbox(unseen=m["unseen"], unread=m["unread"], recent_unread=m["recent_unread"], msg=m)

            # Typing
            elif mtype == "typ" or mtype == "ttyp":
                author_id = str(m.get("from"))
                thread_id = m.get("thread_fbid")
                if thread_id:
                    thread_type = ThreadType.GROUP
                    thread_id = str(thread_id)
                else:
                    thread_type = ThreadType.USER
                    if author_id == self.uid:
                        thread_id = m.get("to")
                    else:
                        thread_id = author_id
                typing_status = TypingStatus(m.get("st"))
                self.onTyping(author_id=author_id, status=typing_status, thread_id=thread_id, thread_type=thread_type, msg=m)

            # Delivered

            # Seen
            # elif mtype == "m_read_receipt":
            #
            #     self.onSeen(m.get('realtime_viewer_fbid'), m.get('reader'), m.get('time'))

            elif mtype in ['jewel_requests_add']:
                from_id = m['from']
                self.onFriendRequest(from_id=from_id, msg=m)

            # Happens on every login
            elif mtype == "qprimer":
                self.onQprimer(ts=m.get("made"), msg=m)

            # Is sent before any other message
            elif mtype == "deltaflow":
                pass

            # Chat timestamp
            elif mtype == "chatproxy-presence":
                buddylist = {}
                for _id in m.get('buddyList', {}):
                    payload = m['buddyList'][_id]
                    buddylist[_id] = payload.get('lat')
                self.onChatTimestamp(buddylist=buddylist, msg=m)

            # Unknown message type
            else:
                self.onUnknownMesssageType(msg=m)

        except Exception as e:
            self.onMessageError(exception=e, msg=m)

#==================================================================================================================================================

saved_stuff = {}

def setup(bot):
    saved_stuff["parse"] = fbchat.Client._parseMessage
    fbchat.Client._parseMessage = _parseMessage

def teardown(bot):
    fbchat.Client._parseMessage = saved_stuff["parse"]
