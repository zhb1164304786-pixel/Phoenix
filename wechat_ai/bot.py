"""微信 AI 自动回复

    python bot.py          连接电脑上的微信，开始帮你自动回复
    python bot.py --test   不连微信，在这个窗口里扮演朋友，先试试 AI 怎么回
"""

import sys
import time
from collections import defaultdict, deque

import anthropic

import config
from ai_reply import make_reply

# 每次把最近多少条聊天记录交给 AI 参考
HISTORY_SIZE = 20

KEY_HELP = (
    "Claude 密钥不对或没设置。\n"
    "请先按 README 里的步骤设置 ANTHROPIC_API_KEY，然后关掉这个窗口重新打开再运行。"
)


def strip_label(text):
    """去掉自动回复前面的 [AI代回] 标记，免得 AI 学着在回复里重复它。"""
    if config.AI_LABEL and text.startswith(config.AI_LABEL):
        return text[len(config.AI_LABEL):]
    return text


class RateLimiter:
    """记录每个人最近一小时收到了几条自动回复。"""

    def __init__(self, per_hour):
        self.per_hour = per_hour
        self.sent = defaultdict(deque)

    def allow(self, who):
        now = time.time()
        times = self.sent[who]
        while times and now - times[0] > 3600:
            times.popleft()
        return len(times) < self.per_hour

    def record(self, who):
        self.sent[who].append(time.time())


# ---------- 测试模式：不连微信 ----------

def run_test():
    print("测试模式：你来扮演朋友，打字后按回车，看看 AI 会怎么回。")
    print("直接关掉窗口或按 Ctrl+C 结束。\n")
    history = []
    while True:
        try:
            text = input("朋友：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        history.append(("friend", text))
        try:
            reply = make_reply(history[-HISTORY_SIZE:])
        except anthropic.AuthenticationError:
            print(KEY_HELP)
            return
        except anthropic.APIError as e:
            print(f"（调用 Claude 出错：{e}）")
            continue
        if reply is None:
            print("（AI 这次选择不回复）")
            continue
        print(f"AI：  {config.AI_LABEL}{reply}\n")
        history.append(("me", reply))


# ---------- 正式模式：连接微信 ----------

def names_with_new_messages(wx, watching):
    """在微信左侧的会话列表里，找出白名单里有新消息的人。"""
    names = []
    for session in wx.GetSession():
        isnew = session.isnew
        if callable(isnew):
            isnew = isnew()
        if isnew and session.name in watching:
            names.append(session.name)
    return names


def read_chat(wx):
    """读取当前打开的聊天窗口，整理成 [(who, text), ...]。"""
    from wxauto4.msgs import FriendMessage, SelfMessage, TextMessage

    history = []
    for msg in wx.GetAllMessage():
        if isinstance(msg, FriendMessage):
            who = "friend"
        elif isinstance(msg, SelfMessage):
            who = "me"
        else:
            continue  # 时间、系统提示之类的不算聊天内容
        if isinstance(msg, TextMessage):
            text = msg.content
        else:
            text = f"[非文字消息：{msg.type}]"
        if who == "me":
            text = strip_label(text)
        history.append((who, text))
    return history


def handle_chat(wx, name, limiter):
    wx.ChatWith(name)
    history = read_chat(wx)

    # 最后一条是自己发的（你已经亲自回过，或 AI 回过），就不用再回
    if not history or history[-1][0] != "friend":
        return

    print(f"\n{name}：{history[-1][1]}")
    if not limiter.allow(name):
        print(f"  （一小时内已经自动回复 {name} {limiter.per_hour} 条了，这条先不回）")
        return

    reply = make_reply(history[-HISTORY_SIZE:])
    if reply is None:
        print("  （AI 这次选择不回复）")
        return

    # 带上 who，确保发给对的人，即使你中途点开了别的聊天
    wx.SendMsg(config.AI_LABEL + reply, who=name, exact=True)
    limiter.record(name)
    print(f"  已回复：{reply}")


def run_wechat():
    if sys.platform != "win32":
        print("连接微信需要在 Windows 电脑上运行，并且已经登录微信电脑版。")
        print("在其他电脑上可以先用 python bot.py --test 试试 AI 的回复。")
        return
    if not config.WHITELIST:
        print("还没设置要自动回复谁。请打开 config.py，把对方的名字填进 WHITELIST。")
        return

    from wxauto4 import WeChat

    wx = WeChat()
    limiter = RateLimiter(config.MAX_REPLIES_PER_HOUR)
    watching = set(config.WHITELIST)
    print(f"已连接微信，正在帮你回复：{'、'.join(config.WHITELIST)}")
    print("运行期间请不要操作微信窗口。按 Ctrl+C 停止。")

    try:
        while True:
            try:
                for name in names_with_new_messages(wx, watching):
                    handle_chat(wx, name, limiter)
            except anthropic.AuthenticationError:
                print(KEY_HELP)
                return
            except Exception as e:
                print(f"出错了：{e}。30 秒后再试。")
                time.sleep(30)
                continue
            time.sleep(config.CHECK_EVERY_SECONDS)
    except KeyboardInterrupt:
        print("\n已停止自动回复。")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    else:
        run_wechat()
