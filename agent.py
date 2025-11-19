"""
Assembly Agent for Content Studio Multi-Agent System
Combines video, voiceover, and background music into a final production

This agent:
- Receives video, voiceover, and music file URLs
- Downloads all media files
- Synchronizes timing (loops/trims music, pads voice)
- Mixes audio tracks (voiceover at 100%, music at 30%)
- Combines audio with video using FFmpeg
- Uploads final video and returns URL
"""

import os
import subprocess
import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional
from dotenv import load_dotenv
import httpx

from uagents import Agent, Context, Model
from gcs_storage import upload_to_storage, is_storage_configured

# Load environment variables
load_dotenv()

# Check GCS configuration
if not is_storage_configured():
    raise ValueError("GCS not configured. Add GCS_BUCKET_NAME and GOOGLE_CLOUD_PROJECT to .env")

# Create temp directory for processing
TEMP_DIR = Path("./temp_assembly")
TEMP_DIR.mkdir(exist_ok=True)

# Create agent
agent = Agent(
    name="assembly_agent",
    seed="assembly-agent-seed-phrase-12345",
    port=8005,
    mailbox=True
)


# ========== MESSAGE MODELS ==========

class AssemblyRequest(Model):
    """Request to assemble media components"""
    request_id: str
    video_url: str
    voiceover_url: str
    music_url: str
    script: Optional[str] = None


class AssemblyResponse(Model):
    """Response with assembled video"""
    request_id: str
    final_video_url: str
    duration: float
    status: str
    error: Optional[str] = None


# ========== HELPER FUNCTIONS ==========

async def download_file(url: str, output_path: Path) -> Path:
    """Download a file from URL"""
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        return output_path


def get_duration(media_path: Path) -> float:
    """Get duration of audio/video file using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(media_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0.0


def adjust_audio_duration(audio_path: Path, target_duration: float, output_path: Path) -> Path:
    """Adjust audio to match target duration (loop if shorter, trim if longer)"""
    current_duration = get_duration(audio_path)
    
    if current_duration == 0:
        raise ValueError(f"Could not get duration for {audio_path}")
    
    # If very close, just use as-is
    if abs(current_duration - target_duration) < 1.0:
        return audio_path
    
    # If shorter, loop it
    if current_duration < target_duration:
        # Pad with silence if target is longer
        cmd = [
            'ffmpeg',
            '-i', str(audio_path),
            '-f', 'lavfi',
            '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
            '-filter_complex', f'[0:a][1:a]concat=n=2:v=0:a=1[out]',
            '-map', '[out]',
            '-t', str(target_duration),
            '-y',
            str(output_path)
        ]
    else:
        # Trim if target is shorter (re-encode for WAV)
        cmd = [
            'ffmpeg',
            '-i', str(audio_path),
            '-t', str(target_duration),
            '-y',
            str(output_path)
        ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def combine_media(video_path: Path, voiceover_path: Path, music_path: Path, output_path: Path) -> Path:
    """
    Combine video with voiceover and background music
    
    Audio mixing:
    - Voiceover at 100% volume
    - Music at 30% volume (background)
    - Mix both tracks together
    """
    
    cmd = [
        'ffmpeg',
        '-i', str(video_path),           # Input video
        '-i', str(voiceover_path),       # Input voiceover
        '-i', str(music_path),           # Input music
        '-filter_complex',
        # Normalize sample rates and channels, then mix
        '[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=1.0[voice];'
        '[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.25[music];'
        '[voice][music]amix=inputs=2:duration=longest:dropout_transition=2:normalize=0[audio]',
        '-map', '0:v',                   # Use video from first input
        '-map', '[audio]',               # Use mixed audio
        '-c:v', 'copy',                  # Copy video codec (no re-encoding)
        '-c:a', 'aac',                   # Encode audio as AAC
        '-b:a', '192k',                  # Audio bitrate
        '-ar', '48000',                  # Sample rate
        '-shortest',                     # Match shortest input duration
        '-y',                            # Overwrite output
        str(output_path)
    ]
    
    print(f"Running FFmpeg command...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")
    
    return output_path


def upload_final_video(file_path: Path, ctx: Context) -> str:
    """Upload file to GCS and return URL"""
    
    # Read file
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    # Upload to GCS
    filename = f"final_video_{int(datetime.now().timestamp())}_{uuid4().hex[:8]}.mp4"
    
    # Import from gcs_storage module
    from gcs_storage import upload_to_storage as gcs_upload
    
    url = gcs_upload(
        file_data=file_data,
        filename=filename,
        content_type="video/mp4"
    )
    
    return url


# ========== AGENT HANDLERS ==========

@agent.on_event("startup")
async def startup(ctx: Context):
    """Initialize assembly agent"""
    ctx.logger.info("🎬 Starting Assembly Agent...")
    ctx.logger.info(f"📍 Agent address: {agent.address}")
    ctx.logger.info("✅ Ready to assemble media components")


@agent.on_message(model=AssemblyRequest)
async def handle_assembly_request(ctx: Context, sender: str, msg: AssemblyRequest):
    """Handle media assembly request"""
    
    ctx.logger.info(f"📨 Assembly request from {sender[:12]}...")
    ctx.logger.info(f"   Request ID: {msg.request_id}")
    ctx.logger.info(f"   Video: {msg.video_url[:50]}...")
    ctx.logger.info(f"   Voice: {msg.voiceover_url[:50]}...")
    ctx.logger.info(f"   Music: {msg.music_url[:50]}...")
    
    try:
        # Create unique work directory
        work_dir = TEMP_DIR / msg.request_id
        work_dir.mkdir(exist_ok=True)
        
        # Step 1: Download all files
        ctx.logger.info("⬇️  Downloading media files...")
        
        video_path = work_dir / "video.mp4"
        voice_path = work_dir / "voiceover.mp3"
        music_path = work_dir / "music.mp3"
        
        await download_file(msg.video_url, video_path)
        ctx.logger.info("   ✅ Video downloaded")
        
        await download_file(msg.voiceover_url, voice_path)
        ctx.logger.info("   ✅ Voiceover downloaded")
        
        await download_file(msg.music_url, music_path)
        ctx.logger.info("   ✅ Music downloaded")
        
        # Step 2: Check durations
        ctx.logger.info("⏱️  Checking durations...")
        
        video_duration = get_duration(video_path)
        voice_duration = get_duration(voice_path)
        music_duration = get_duration(music_path)
        
        ctx.logger.info(f"   Video: {video_duration:.1f}s")
        ctx.logger.info(f"   Voice: {voice_duration:.1f}s")
        ctx.logger.info(f"   Music: {music_duration:.1f}s")
        
        # Step 3: Synchronize timing (use video duration as target)
        ctx.logger.info("🔄 Synchronizing audio timing...")
        
        target_duration = video_duration
        
        # Adjust music to match video length
        music_adjusted_path = work_dir / "music_adjusted.mp3"
        adjust_audio_duration(music_path, target_duration, music_adjusted_path)
        ctx.logger.info("   ✅ Music adjusted")
        
        # Adjust voice if needed (pad with silence if shorter)
        voice_adjusted_path = work_dir / "voice_adjusted.mp3"
        if voice_duration < target_duration:
            adjust_audio_duration(voice_path, target_duration, voice_adjusted_path)
            ctx.logger.info("   ✅ Voiceover adjusted")
        else:
            voice_adjusted_path = voice_path
        
        # Step 4: Combine everything
        ctx.logger.info("🎬 Combining video + voice + music...")
        
        output_path = work_dir / "final_video.mp4"
        combine_media(
            video_path=video_path,
            voiceover_path=voice_adjusted_path,
            music_path=music_adjusted_path,
            output_path=output_path
        )
        
        ctx.logger.info("   ✅ Media combined successfully!")
        
        # Step 5: Upload to GCS
        ctx.logger.info("⬆️  Uploading final video to GCS...")
        
        final_url = upload_final_video(output_path, ctx)
        final_duration = get_duration(output_path)
        
        ctx.logger.info(f"   ✅ Upload complete: {final_url[:50]}...")
        ctx.logger.info(f"   Duration: {final_duration:.1f}s")
        
        # Step 6: Send response
        response = AssemblyResponse(
            request_id=msg.request_id,
            final_video_url=final_url,
            duration=final_duration,
            status="complete"
        )
        
        await ctx.send(sender, response)
        ctx.logger.info("✅ Assembly complete and sent to coordinator!")
        
        # Cleanup temp files
        import shutil
        shutil.rmtree(work_dir)
        ctx.logger.info("🧹 Temp files cleaned up")
        
    except Exception as e:
        ctx.logger.error(f"❌ Assembly failed: {e}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        
        # Send error response
        error_response = AssemblyResponse(
            request_id=msg.request_id,
            final_video_url="",
            duration=0.0,
            status="error",
            error=str(e)
        )
        
        await ctx.send(sender, error_response)


if __name__ == "__main__":
    print("🎬 Starting Assembly Agent...")
    print(f"📍 Agent address: {agent.address}")
    print()
    print("🎯 This agent assembles video + voiceover + music")
    print("   Uses FFmpeg to combine and sync all media")
    print()
    print("📝 Requirements:")
    print("   - FFmpeg installed (brew install ffmpeg)")
    print("   - AGENTVERSE_API_KEY in .env")
    print()
    print("✅ Agent is running on port 8010")
    print("   Press Ctrl+C to stop.\n")
    
    agent.run()
