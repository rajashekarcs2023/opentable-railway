"""
Real Music Agent using Lyria RealTime
Generates actual music and uploads to GCS
With chat protocol for testing
"""

import os
import asyncio
import wave
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

from uagents import Agent, Context, Protocol, Model
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    chat_protocol_spec
)
from gcs_storage import upload_to_storage, is_storage_configured

load_dotenv()

# Check configurations
if not is_storage_configured():
    raise ValueError("GCS not configured. Add GCS_BUCKET_NAME and GOOGLE_CLOUD_PROJECT to .env")

gemini_api_key = os.getenv('GEMINI_API_KEY')
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

# Initialize Gemini client with alpha API version for Lyria
client = genai.Client(http_options={'api_version': 'v1alpha'}, api_key=gemini_api_key)

# Model configuration
LYRIA_MODEL = 'models/lyria-realtime-exp'
SAMPLE_RATE = 48000  # 48kHz
CHANNELS = 2  # Stereo

# Create agent
agent = Agent(
    name="real_music",
    seed="real-music-seed2020-2025",
    port=8017,
    mailbox=True
)

# Initialize chat protocol
chat_proto = Protocol(spec=chat_protocol_spec)


class MusicRequest(Model):
    """Request to music agent"""
    request_id: str
    prompt: str
    duration: int


class MusicResponse(Model):
    """Response from music agent"""
    request_id: str
    audio_url: str
    duration: float


def save_pcm_as_wav(pcm_data: bytes, filename: str):
    """Convert raw PCM data to WAV file"""
    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_data)


@agent.on_event("startup")
async def startup(ctx: Context):
    """Initialize agent"""
    ctx.logger.info("🎵 Starting Real Music Agent (Lyria RealTime)...")
    ctx.logger.info(f"📍 Agent address: {agent.address}")
    ctx.logger.info("✅ Ready to generate real music")


@chat_proto.on_message(ChatMessage)
async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handle chat messages for testing"""
    # Extract text from message
    text_parts = [part.text for part in msg.content if hasattr(part, 'text')]
    user_text = " ".join(text_parts) if text_parts else ""
    
    ctx.logger.info(f"💬 Chat message: {user_text[:100]}...")
    
    if not user_text:
        ctx.logger.warning("⚠️ Empty message")
        return
    
    # Parse prompt and duration from text
    # Format: "prompt text | duration"
    # Example: "upbeat happy music | 5"
    if "|" in user_text:
        parts = user_text.split("|")
        prompt = parts[0].strip()
        try:
            duration = int(parts[1].strip())
        except:
            duration = 5  # Default 5 seconds
    else:
        prompt = user_text.strip()
        duration = 5  # Default 5 seconds
    
    ctx.logger.info(f"   Prompt: {prompt}")
    ctx.logger.info(f"   Duration: {duration}s")
    
    # Generate music
    request_id = f"chat_{int(datetime.now().timestamp())}"
    await process_music_request(ctx, sender, request_id, prompt, duration, is_chat=True)


@agent.on_message(MusicRequest)
async def handle_music_request(ctx: Context, sender: str, msg: MusicRequest):
    """Handle music generation request"""
    ctx.logger.info(f"📨 Music request: {msg.prompt[:50]}...")
    await process_music_request(ctx, sender, msg.request_id, msg.prompt, msg.duration, is_chat=False)


async def process_music_request(ctx: Context, sender: str, request_id: str, prompt: str, duration: int, is_chat: bool):
    """Process music generation request"""
    try:
        ctx.logger.info(f"🎵 Generating music with Lyria RealTime...")
        ctx.logger.info(f"   Prompt: {prompt}")
        ctx.logger.info(f"   Duration: {duration}s")
        
        audio_chunks = []
        is_collecting = True
        
        async def receive_audio(session):
            """Collect audio chunks"""
            try:
                message_count = 0
                async for message in session.receive():
                    message_count += 1
                    if not is_collecting:
                        break
                    
                    # DIAGNOSTIC: Log message details
                    ctx.logger.info(f"   📩 Message {message_count}: {type(message).__name__}")
                    
                    if (hasattr(message, 'server_content') and 
                        message.server_content is not None and 
                        hasattr(message.server_content, 'audio_chunks') and
                        message.server_content.audio_chunks):
                        ctx.logger.info(f"      Audio chunks in message: {len(message.server_content.audio_chunks)}")
                        for chunk in message.server_content.audio_chunks:
                            audio_chunks.append(chunk.data)
                    else:
                        ctx.logger.warning(f"      ⚠️ Message has no audio_chunks!")
                        if hasattr(message, 'server_content'):
                            ctx.logger.warning(f"      server_content: {message.server_content}")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                ctx.logger.error(f"❌ Error receiving audio: {e}")
                import traceback
                ctx.logger.error(traceback.format_exc())
        
        # Connect and generate
        try:
            ctx.logger.info(f"🔌 Connecting to Lyria API...")
            async with client.aio.live.music.connect(model=LYRIA_MODEL) as session:
                ctx.logger.info(f"✅ Connected to Lyria session")
                receiver_task = asyncio.create_task(receive_audio(session))
                
                try:
                    # Send prompts and config
                    ctx.logger.info(f"📝 Setting prompts...")
                    await session.set_weighted_prompts(
                        prompts=[types.WeightedPrompt(text=prompt, weight=1.0)]
                    )
                    
                    ctx.logger.info(f"⚙️  Setting config...")
                    await session.set_music_generation_config(
                        config=types.LiveMusicGenerationConfig(
                            bpm=120,
                            temperature=1.0,
                            music_generation_mode=types.MusicGenerationMode.QUALITY
                        )
                    )
                    
                    # Start streaming
                    ctx.logger.info(f"▶️  Starting playback...")
                    await session.play()
                    ctx.logger.info(f"🎵 Streaming music for {duration}s...")
                    
                    # Collect for requested duration
                    await asyncio.sleep(duration)
                    
                    # Stop streaming
                    is_collecting = False
                    await session.stop()
                    
                    # Wait a bit for final chunks
                    await asyncio.sleep(1)
                    
                    ctx.logger.info(f"✅ Collected {len(audio_chunks)} audio chunks")
                    
                finally:
                    receiver_task.cancel()
                    try:
                        await receiver_task
                    except asyncio.CancelledError:
                        pass
        
        except Exception as api_error:
            ctx.logger.error(f"❌ Lyria API connection error: {api_error}")
            import traceback
            ctx.logger.error(traceback.format_exc())
            if not is_chat:
                await ctx.send(sender, MusicResponse(request_id=request_id, audio_url="", duration=0))
            return
        
        if not audio_chunks:
            ctx.logger.error("❌ No audio generated")
            if not is_chat:
                await ctx.send(sender, MusicResponse(request_id=request_id, audio_url="", duration=0))
            return
        
        # DIAGNOSTIC: Log chunk collection details
        ctx.logger.info(f"✅ Collected {len(audio_chunks)} audio chunks")
        
        # Log first 3 chunks
        for i in range(min(3, len(audio_chunks))):
            chunk = audio_chunks[i]
            ctx.logger.info(f"   Chunk {i+1}: {len(chunk)} bytes")
            if i == 0:
                ctx.logger.info(f"      First 16 bytes (hex): {chunk[:16].hex()}")
                has_riff = chunk[:4] == b'RIFF'
                ctx.logger.info(f"      Has WAV header (RIFF): {has_riff}")
        
        # Combine audio chunks
        pcm_data = b''.join(audio_chunks)
        
        # Expected size: 48kHz * 2 channels * 2 bytes/sample * duration
        expected_size = 48000 * 2 * 2 * duration
        ctx.logger.info(f"✅ Combined PCM: {len(pcm_data)} bytes")
        ctx.logger.info(f"   Expected size: ~{expected_size} bytes for {duration}s")
        ctx.logger.info(f"   Size match: {abs(len(pcm_data) - expected_size) / expected_size * 100:.1f}% difference")
        
        # Convert to WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = tmp.name
        
        save_pcm_as_wav(pcm_data, temp_path)
        
        # Read WAV bytes
        with open(temp_path, 'rb') as f:
            wav_data = f.read()
        
        os.remove(temp_path)
        ctx.logger.info(f"✅ WAV file created: {len(wav_data)} bytes")
        
        # Upload to GCS
        ctx.logger.info("📤 Uploading to GCS...")
        filename = f"real_music_{int(datetime.now().timestamp())}.wav"
        music_url = upload_to_storage(
            file_data=wav_data,
            filename=filename,
            content_type="audio/wav"
        )
        
        ctx.logger.info(f"✅ Music URL: {music_url}")
        
        # Send response
        if is_chat:
            response_text = f"✅ Music Generated!\n🎵 URL: {music_url}\n⏱️  Duration: {duration}s"
            await ctx.send(sender, ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid4(),
                content=[TextContent(text=response_text, type="text")]
            ))
        else:
            await ctx.send(sender, MusicResponse(
                request_id=request_id,
                audio_url=music_url,
                duration=float(duration)
            ))
        
        ctx.logger.info("✅ Response sent!")
        
    except Exception as e:
        ctx.logger.error(f"❌ Error: {e}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        
        if not is_chat:
            await ctx.send(sender, MusicResponse(request_id=request_id, audio_url="", duration=0))


@chat_proto.on_message(ChatAcknowledgement)
async def handle_acknowledgement(ctx: Context, sender: str, msg: ChatAcknowledgement):
    """Handle message acknowledgements"""
    ctx.logger.debug(f"✓ Message acknowledged by {sender[:12]}...")


# Include chat protocol
agent.include(chat_proto, publish_manifest=True)


if __name__ == "__main__":
    print("🎵 Starting Real Music Agent (Lyria RealTime)...")
    print(f"📍 Agent address: {agent.address}")
    print("✅ Agent running\n")
    print("💬 Chat format: 'your prompt | duration_seconds'")
    print("   Example: 'upbeat happy music | 10'\n")
    
    agent.run()
