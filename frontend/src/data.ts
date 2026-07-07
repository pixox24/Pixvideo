export const VOICE_OPTIONS = {
  edge: [
    { id: "zh-CN-XiaoxiaoNeural", name: "晓晓 (女声 - 温暖亲切)", desc: "Edge TTS 推荐女声" },
    { id: "zh-CN-YunxiNeural", name: "云希 (男声 - 科技讲解)", desc: "最适合科技、产品科普" },
    { id: "zh-CN-YunjianNeural", name: "云健 (男声 - 新闻播报)", desc: "正式语气，节奏稳健" },
    { id: "zh-HK-HiuMaanNeural", name: "晓佳 (粤语 - 甜美女性)", desc: "粤语讲解、故事播报" },
  ],
  minimax: [
    { id: "male-qn-qingse", name: "MiniMax 青涩男声", desc: "清晰自然，适合科普讲解" },
    { id: "female-shaonv", name: "MiniMax 少女声", desc: "轻快明亮，适合生活内容" },
    { id: "male-qn-jingying", name: "MiniMax 精英男声", desc: "稳重正式，适合商业叙事" },
  ],
  comfyui: [
    { id: "comfy-custom-voice1", name: "自定义参考音频 (根据上传克隆)", desc: "由 ComfyUI Audio-Prompt 提取特征" },
  ],
};
