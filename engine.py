# engine.py - The "Audio-First" Unlimited Version
from fastapi import FastAPI, BackgroundTasks
import yt_dlp
import os
import uuid
import uvicorn
import json
from groq import Groq
from dotenv import load_dotenv

# Load API Key
load_dotenv()
# Ensure GROQ_API_KEY is in your .env file!

app = FastAPI()
jobs = {}

# --- HELPER FUNCTIONS ---

def download_audio_only(url, job_id):
    """
    Downloads ONLY the audio for the whole video. 
    Fast (even for 2 hour videos).
    """
    os.makedirs("temp_audio", exist_ok=True)
    audio_path = f"temp_audio/{job_id}" # yt-dlp adds extension auto
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': audio_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'overwrites': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    return f"{audio_path}.mp3"

def transcribe_audio(audio_path):
    """Sends audio to Groq (Whisper) for full text"""
    client = Groq()
    with open(audio_path, "rb") as f:
        # Whisper Large V3 handles long files well
        return client.audio.transcriptions.create(
            file=f, model="whisper-large-v3"
        ).text

def get_ai_timestamps(transcript):
    """Asks Llama 3 to find the best clip in the WHOLE text"""
    client = Groq()
    # We ask for a clip between 30-60 seconds
    prompt = f"""
    Analyze this transcript. Find the ONE most viral/shareable segment (30-60s duration).
    Return STRICT JSON: {{"start": <float_seconds>, "end": <float_seconds>, "topic": "<title>", "reason": "<why>"}}
    
    Transcript:
    {transcript[:25000]} 
    """
    # Note: If transcript is HUGE, you might need to chunk it, 
    # but 25k chars covers a lot of dense talking.
    
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    content = completion.choices[0].message.content
    content = content.replace("```json", "").replace("```", "").strip()
    return json.loads(content)

def download_specific_clip(url, start, end, job_id):
    """
    Downloads ONLY the specific video segment in HD.
    Does NOT download the whole video.
    """
    os.makedirs("downloads", exist_ok=True)
    output_path = f"downloads/{job_id}.mp4"
    
    ydl_opts = {
        'format': 'best[ext=mp4]', # Get High Quality Video
        'outtmpl': output_path,
        'download_ranges': lambda info, *args: [{'start_time': start, 'end_time': end}],
        'force_keyframes_at_cuts': False, # False = Fast/Direct Cut
        'quiet': True,
        'overwrites': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    return output_path

# --- MAIN PIPELINE ---

def run_pipeline(job_id, url):
    try:
        # 1. Download Audio (Fast)
        jobs[job_id] = {"status": "downloading_audio"}
        print(f"🎧 {job_id}: Downloading Full Audio...")
        audio_path = download_audio_only(url, job_id)
        
        # 2. Transcribe
        jobs[job_id]["status"] = "transcribing"
        print(f"🧠 {job_id}: Transcribing Audio...")
        transcript = transcribe_audio(audio_path)
        
        # 3. AI Analysis
        jobs[job_id]["status"] = "analyzing"
        print(f"🤖 {job_id}: finding viral clip...")
        ai_data = get_ai_timestamps(transcript)
        print(f"🎯 {job_id}: Found clip at {ai_data['start']}s - '{ai_data['topic']}'")
        
        # 4. Download HD Clip
        jobs[job_id]["status"] = "cutting"
        print(f"✂️ {job_id}: Downloading HD Segment...")
        final_file = download_specific_clip(url, ai_data['start'], ai_data['end'], job_id)
        
        # Cleanup Audio Temp File
        if os.path.exists(audio_path): os.remove(audio_path)
        
        jobs[job_id] = {
            "status": "completed",
            "file": final_file,
            "data": ai_data
        }
        print(f"✅ {job_id}: Pipeline Finished!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        jobs[job_id] = {"status": "failed", "error": str(e)}

@app.post("/process")
async def start_process(url: str, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "queued"}
    background_tasks.add_task(run_pipeline, job_id, url)
    return {"job_id": job_id}

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    return jobs.get(job_id, {"status": "not_found"})

if __name__ == "__main__":
    print("🚀 UNLIMITED ENGINE READY (Port 8000)")
    uvicorn.run(app, host="0.0.0.0", port=8000)
