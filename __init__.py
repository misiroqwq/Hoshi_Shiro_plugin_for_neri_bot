import time
import jieba
from pathlib import Path
import random
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
try:
    import ujson as json
except ModuleNotFoundError:
    import json

from nonebot import on_notice, on_message, on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import PokeNotifyEvent, Message ,GroupMessageEvent
from nonebot.adapters.onebot.v11.permission import GROUP
from nonebot.adapters.onebot.v11.message import Message, MessageSegment
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_session import EventSession


__plugin_usage__ = """
usage：
    1. 戳一戳随机掉落星白语录
    2. 发送星白随机语音
        指令：
        * 随机语音?[狩叶/春香|诺瓦|真白|音理|房东|鹰世|野鸟/珍妮弗|花江]
            ps.如果不指定人物，则从狩叶、诺瓦、真白、音理中任选一条。
        * 语音文本 --显示上一条发送语音的文本内容
        示例：
            随机语音
            随机语音狩叶
            随机语音诺瓦
            语音文本
    3. 群消息有概率发送语录
"""

#=================CONFIG=================
# 戳一戳 cd
POKE_CD = 15

# 至少要等多少条消息后才允许发送文本
TEXT_SEND_FREQUENCY = 10

# 模糊匹配要等消息长度至少为多少的信息
MATCH_MSG_LENGTH = 4


# 转换用，勿改
NAME_TO_FILE_DICT = {
    '音理':'ner',
    '诺瓦':'noi',
    '真白':'mas',
    '狩叶':'kar',
    '春香':'kar',
    '野鸟':'jib',
    '珍妮弗':'jib',
    '鹰世':'tak',
    '花江':'han',
    '房东':'ooy',
}



class SL_Data_And_Control:
    # 路径
    JSON_PATH = Path(__file__).parent / "json_files"
    text_raw_path = JSON_PATH / "text_raw.json"
    text_jieba_path = JSON_PATH / "text_jieba.json"
    voice_info_path = JSON_PATH / "voice_info.json"
    voice_long_path = JSON_PATH / "voice_long.json"
    text_group_count_path = JSON_PATH / "text_group_count.json"

    # 提取json
    voice_file_path = Path(__file__).parent / "voice_files"
    text_raw = json.loads(text_raw_path.read_text("utf-8")) # 星白所有台词的字典
    text_jieba = json.loads(text_jieba_path.read_text("utf-8")) # jieba 台词，用于模糊匹配
    voice_info = json.loads(voice_info_path.read_text("utf-8")) # 所有语音文件的对应信息
    voice_long = json.loads(voice_long_path.read_text("utf-8")) # 时长大于4秒的长语音文件
    poke__cd_control_dict = {}
    voice__last_voice_text_dict = {}
    text__send_frequency_control_dict = {}
    # text_raw 有多少个键，用于判断随机范围
    text_raw_length = len(text_raw)
    # 模糊匹配相关
    vectorizer = TfidfVectorizer()
    phrase_vectors = vectorizer.fit_transform(text_jieba)
    
    # 戳一戳 cd 控制
    @classmethod
    async def poke_cd_control(cls, group_id: str):
        now_time = time.time()
        last_poke_time = cls.poke__cd_control_dict.get(group_id, 0)
        if now_time - last_poke_time < POKE_CD:
            return False
        else:
            cls.poke__cd_control_dict[group_id] = now_time
            return True
    
    # 记录上一个发送的随机语音的文本
    @classmethod
    async def last_voice_text_control(cls, group_id: str, voice_file_name: str = '', is_get: bool = False):
        if is_get:
            voice_file_name = cls.voice__last_voice_text_dict.get(group_id, '')
            voice_info = cls.voice_info.get(voice_file_name, ['', "未查询到文本..."])
            return voice_info[1]
        else:
            cls.voice__last_voice_text_dict[group_id] = voice_file_name
    
    # 检测消息是否发送，当未回复消息超过10的时候，就可以等待一个长句子来匹配了
    @classmethod
    async def text_send_control(cls, group_id: str, message: str):
        group_send_frequency = cls.text__send_frequency_control_dict.get(group_id, 0)


        if group_send_frequency < TEXT_SEND_FREQUENCY:
            cls.text__send_frequency_control_dict[group_id] = group_send_frequency + 1
            return False
        else:
            if len(message) < MATCH_MSG_LENGTH or "[image]" in message:
                cls.text__send_frequency_control_dict[group_id] += 1
                return False
            else:
                cls.text__send_frequency_control_dict[group_id] = 0
                return True    
    
    # 模糊匹配
    @classmethod
    async def find_most_similar(cls, msg: str):
        """
        查找与输入文本最相似的台词。
        :param query: 用户输入文本
        :return: 最相似的台词

        如果找到的相似度低于0.3，返回随机文本
        """
        # 对用户输入进行分词
        msg = " ".join(jieba.lcut(msg))
        query_vector = cls.vectorizer.transform([msg])

        # 计算余弦相似度
        similarities = cosine_similarity(query_vector, cls.phrase_vectors).flatten()

        # 找到最高相似度的索引
        most_similar_index = similarities.argmax()
        if similarities[most_similar_index] < 0.3: #如果相似度小于0.3，则随机选择一个文本
            send_text = cls.text_raw[str(random.randint(1, cls.text_raw_length))]
        else:
            send_text = cls.text_raw[str(most_similar_index+1)]
        return send_text
    
SL_Utils = SL_Data_And_Control()

#=================事件触发器====================

# 戳一戳插件，戳一戳可以发送随机星白语录
poke_to_text = on_notice(priority=7, block=False)

# 随机语音插件，发送随机星白语音
random_voice = on_command("随机语音", permission=GROUP, priority=5, block=True)
voice_text = on_command("语音文本", permission=GROUP, priority=5, block=True)
specific_voice = on_command("星白语音", permission=GROUP, priority=5, block=True)

# 群友每发一定数量的消息就有概率发送星白语录
send_text = on_message(priority = 12, block = False)

#==============================================
@poke_to_text.handle()
async def _poke_to_text(event: PokeNotifyEvent):
    if event.target_id != event.self_id :
        return
    # cd控制，避免刷屏
    if not await SL_Utils.poke_cd_control(group_id = str(event.group_id)):
        return
    # 获取随机文本
    text = SL_Utils.text_raw[str(random.randint(1, SL_Utils.text_raw_length))]
    await poke_to_text.finish(text)


#==============================================
@random_voice.handle()
async def _random_voice(event: GroupMessageEvent, arg: Message = CommandArg()):
    msg = arg.extract_plain_text().strip()

    #将指令的参数转化成符号
    character = NAME_TO_FILE_DICT.get(msg, '')
    
    if character:
        # 如果指定了 character，则筛选以 character 开头的语音文件
        eligible_voice_list = [i for i in SL_Utils.voice_long if i.startswith(character)]
    else:
        # 如果未指定 character，则筛选在特定前缀列表中的语音文件
        valid_prefixes = {'ner', 'noi', 'mas', 'kar'}
        eligible_voice_list = [i for i in SL_Utils.voice_long if i[:3] in valid_prefixes]

    #随机选择其中一个语音文件
    voice_file_name = random.choice(eligible_voice_list)
    
    #保存语音的文本，供“语音文本”功能使用
    await SL_Utils.last_voice_text_control(group_id = str(event.group_id), voice_file_name = voice_file_name)


    #获取目的语音文件，发送语音
    result = MessageSegment.record(SL_Utils.voice_file_path / voice_file_name)
    await random_voice.send(result)

@voice_text.handle()
async def _voice_text(event: GroupMessageEvent):
    text = await SL_Utils.last_voice_text_control(group_id = str(event.group_id), is_get = True)
    await voice_text.finish(text)


@specific_voice.handle()
async def _(arg: Message = CommandArg()):
    msg = arg.extract_plain_text().strip()
    specific_voice_file_path = SL_Utils.voice_file_path / f"{msg}.mp3"

    if specific_voice_file_path.is_file():
        result = MessageSegment.record(specific_voice_file_path)
        await specific_voice.send(result)
    else:
        await specific_voice.send("无该语音文件")


#==============================================
@send_text.handle()
async def _send_text(session: EventSession, message: UniMsg):
    # 检测消息是否发送，当未回复消息超过10的时候，就可以等待一个长句子来匹配了
    if not await SL_Utils.text_send_control(group_id = str(session.id2), message= str(message)):
        return
    
    # 获取要发送的文本
    text = await SL_Utils.find_most_similar(msg = str(message))
    await send_text.finish(text)

