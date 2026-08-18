export const VOICE_OPTIONS = {
  edge: [
    { id: "zh-CN-XiaoxiaoNeural", name: "晓晓 (女声 - 温暖亲切)", desc: "Edge TTS 推荐女声" },
    { id: "zh-CN-YunxiNeural", name: "云希 (男声 - 科技讲解)", desc: "最适合科技、产品科普" },
    { id: "zh-CN-YunjianNeural", name: "云健 (男声 - 新闻播报)", desc: "正式语气，节奏稳健" },
    { id: "zh-HK-HiuMaanNeural", name: "晓佳 (粤语 - 甜美女性)", desc: "粤语讲解、故事播报" },
  ],
  minimax: [
    { id: "male-qn-qingse", name: "MiniMax 青涩男声", desc: "清晰自然，适合科普讲解" },
    { id: "male-qn-jingying", name: "MiniMax 精英男声", desc: "稳重正式，适合商业叙事" },
    { id: "male-qn-daxuesheng", name: "MiniMax 大学生男声", desc: "年轻自然，适合口播内容" },
    { id: "female-shaonv", name: "MiniMax 少女声", desc: "轻快明亮，适合生活内容" },
    { id: "female-yujie", name: "MiniMax 御姐声", desc: "成熟清亮，适合品牌叙事" },
    { id: "female-chengshu", name: "MiniMax 成熟女声", desc: "稳重亲和，适合知识讲解" },
    { id: "female-tianmei", name: "MiniMax 甜美女声", desc: "甜美轻快，适合种草短视频" },
    { id: "Chinese (Mandarin)_News_Anchor", name: "中文新闻主播", desc: "标准播报语气" },
    { id: "Chinese (Mandarin)_Warm_Girl", name: "中文温暖女声", desc: "温柔自然" },
    { id: "Chinese (Mandarin)_Gentleman", name: "中文绅士男声", desc: "沉稳商务" },
  ],
  mimo: [
    { id: "mimo_default", name: "MiMo 默认音色", desc: "中国集群默认为「冰糖」，其他集群为「Mia」" },
    { id: "冰糖", name: "冰糖 (中文女声)", desc: "中文女性音色" },
    { id: "茉莉", name: "茉莉 (中文女声)", desc: "中文女性音色" },
    { id: "苏打", name: "苏打 (中文男声)", desc: "中文男性音色" },
    { id: "白桦", name: "白桦 (中文男声)", desc: "中文男性音色" },
    { id: "Mia", name: "Mia (英文女声)", desc: "英文女性音色" },
    { id: "Chloe", name: "Chloe (英文女声)", desc: "英文女性音色" },
    { id: "Milo", name: "Milo (英文男声)", desc: "英文男性音色" },
    { id: "Dean", name: "Dean (英文男声)", desc: "英文男性音色" },
  ],
  qwen_audio: [
    { id: "Cherry", name: "Cherry（中文女声）", desc: "Qwen3-TTS 默认音色" },
    { id: "Serena", name: "Serena（英文女声）", desc: "Qwen3-TTS 英文音色" },
    { id: "Ethan", name: "Ethan（男声）", desc: "Qwen3-TTS 男声音色" },
  ],
  comfyui: [
    { id: "comfy-custom-voice1", name: "自定义参考音频 (根据上传克隆)", desc: "由 ComfyUI Audio-Prompt 提取特征" },
  ],
};
