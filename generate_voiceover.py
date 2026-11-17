import asyncio
import json
import sys
from pathlib import Path

TOOLKIT_DIR = Path(r"E:\researchcode\llm\video_tts_toolkit")
sys.path.insert(0, str(TOOLKIT_DIR))

from tts_video_pipeline import VideoTTSPipeline


async def main():
    project_dir = Path(__file__).parent
    script_path = project_dir / "video_script.json"
    audio_dir = project_dir / "output" / "audio"

    with open(script_path, "r", encoding="utf-8") as f:
        script_items = json.load(f)

    pipeline = VideoTTSPipeline(
        voice="zh-CN-YunxiNeural",
        rate="+10%",
        output_dir=str(audio_dir),
    )

    gaps = [0.6, 0.6, 0.6, 0.6, 0.6, 1.0]
    result = await pipeline.process_script(script_items, custom_gaps=gaps)

    # 补充字幕文本到 timeline_map.json，方便后续生成 ASS 字幕
    subtitle_map = {item["id"]: item.get("subtitle", item["text"]) for item in script_items}
    for entry in result["scenes"]:
        entry["subtitle"] = subtitle_map.get(entry["id"], entry["text"])

    timeline_path = audio_dir / "timeline_map.json"
    timeline_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] 配音与时间轴生成完成，总时长: {result['totalDuration']:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
