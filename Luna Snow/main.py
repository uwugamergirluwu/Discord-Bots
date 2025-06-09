import os
import discord
from discord.ext import commands
from discord import app_commands
from discord import Embed
from dotenv import load_dotenv
import yt_dlp
import asyncio
from asyncio import Lock
from collections import deque
import random
import subprocess
import json
import validators
import requests


load_dotenv()
TOKEN= os.getenv("DISCORD_TOKEN")
#YOUTUBE_URL_REGEX = r"(https)?://(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/embed/)?[^\s&]+"
SONG_QUEUES = {}
QUEUE_LOCKS = {}

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} is online and ready to use!")
    for command in bot.tree.get_commands():
        print(f" - {command.name}: {command.description}")

"""
@bot.event
async def on_message(msg):
    if msg.author.id != bot.user.id:
        await msg.channel.send(f"{msg.author.mention} sup")

@bot.tree.command(name="greet", description="Sends a greeting to the user")
async def greet(interaction: discord.Interaction):
    username = interaction.user.mention
    await interaction.response.send_message(f"{username} Greetings")
"""

async def play_join_voiceline(voice_client, guild_id, channel):
    # Select a voiceline randomly
    random_join_paths = [r"bin\voicelines\luna_snow_join1.mp3",r"bin\voicelines\luna_snow_join2.mp3"]
    join_audio_path = random.choice(random_join_paths)
    await add_to_queue(guild_id, join_audio_path, "Join Voiceline", is_voiceline=True)
    await play_next_song(voice_client, guild_id, channel)

async def play_ult(voice_client, guild_id, channel):
    random_ult_paths = [r"bin\voicelines\luna_snow_ult.mp3", r"bin\voicelines\Luna_snow_ult_friendly.mp3"]
    ult_audio_path = random.choice(random_ult_paths)

    # Add ult voiceline to queue
    await add_to_queue(guild_id, ult_audio_path, "Ult Voiceline", True, True)
    await play_next_song(voice_client, guild_id, channel)

async def play_pause_voiceline(voice_client, pause_audio_path):

    voiceline_source = discord.FFmpegPCMAudio(pause_audio_path, executable=r"bin\ffmpeg\ffmpeg.exe")

    def after_voiceline(error):
        if error:
            print(f"Error playing pause voiceline: {error}")
    voice_client.play(voiceline_source, after=after_voiceline)

@bot.tree.command(name="help", description="Get a list of commands.")
async def help_command(interaction: discord.Interaction):
    embed = Embed(title="❄️ Luna Snow's Commands ❄️", color=0xADD8E6)
    embed.add_field(name="/help", value="View the list of commands.", inline=False)
    embed.add_field(name="/play", value="Play a song or add it to the queue.", inline=False)
    embed.add_field(name="/join", value="Add Luna Snow to a voice channel. If a channel is not specified, she will join the user's channel by default.", inline=False)
    embed.add_field(name="/skip", value="Skip the song Luna is currently playing.", inline=False)
    embed.add_field(name="/pause", value = "Pause the song Luna is currently playing.", inline=False)
    embed.add_field(name="/resume", value="Resume the song Luna is currently paused on.", inline=False)
    embed.add_field(name="/stop", value="Stop the song currently playing and clear the queue. Luna Snow will also leave the voice channel.", inline=False)
    embed.add_field(name="/queue", value="View the current song queue.", inline=False)

@bot.tree.command(name="play", description="Play a song or add it to the queue.")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel
    if voice_channel is None:
        await interaction.followup.send("You must be in a voice channel to use this command.")
        return
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)
    ydl_options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
        "ignoreerrors": True,
    }

    # Check if input query is a Youtube URL
    if validators.url(song_query):
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                track_info = ydl.extract_info(song_query, download=False)
                audio_url = track_info["url"]
                title = track_info.get("title", "Untitled")
        except Exception as e:
            await interaction.followup.send(f"Error fetching the song: {e}")
            return
    else:
        #search youtube if not direct link

        query = "ytsearch1: " + song_query
        results = await search_ytdlp_async(query, ydl_options)
        tracks = results.get("entries", [])

        if tracks is None:
            await interaction.followup.send("No results found for your query.")
            return
        
        first_track = tracks[0]
        audio_url = first_track["url"]
        title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    #Append song to the queue
    await add_to_queue(guild_id, audio_url, title)

    #Check if bot is already in voice channel playing a song
    if not voice_client.is_playing() and not voice_client.is_paused():
        #Play song immediately
        prefix_message = random.choice(["Now it's showtime!", "Time for my biggest hit!"])
        await interaction.followup.send(f"{prefix_message} Now playing: **{title}**")
        await play_ult(voice_client, guild_id, interaction.channel)
    else:
        #Tell user song was added to queue
        await interaction.followup.send(f"Added **{title}** to the queue.")

@bot.tree.command(name="join", description="Luna Snow joins the voice channel.")
async def join(interaction: discord.Interaction, voice_channel: discord.VoiceChannel = None):
    await interaction.response.defer()

    # Get the bot's current voice client and user's voice channel
    voice_client = interaction.guild.voice_client
    user_voice_channel = interaction.user.voice.channel if interaction.user.voice else None
    target_channel = voice_channel or user_voice_channel
    if target_channel is None:
        await interaction.followup.send("You must be in a voice channel or specify a channel for the bot to join.")
        return
    
    # If already connected, move to the target channel if different
    if voice_client:
        if voice_client.channel != target_channel:
            await voice_client.move_to(target_channel)
            await interaction.followup.send(f"Moved to {target_channel.name}.")
            await play_join_voiceline(voice_client, interaction.guild.id, interaction.channel)

        else:
            await interaction.followup.send(f"I'm already in {target_channel.name}.")

    else:
        # Connect to the target channel if not connected
        voice_client = await target_channel.connect()
        await interaction.followup.send(f"Joined {target_channel.name}.")
        await play_join_voiceline(voice_client, interaction.guild.id, interaction.channel)

        
@bot.tree.command(name="skip", description="Skip the current song.")
async def skip(interaction: discord.Interaction):
    await interaction.response.defer()

    voice_client = interaction.guild.voice_client

    #Check if bot is in a voice channel
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        voice_client.stop()
        prefix_skip_message = random.choice(["I've found one of our critics...", "We need to keep rolling!", "No stopping now. Let's move this thing along!"])
        await interaction.followup.send(f"{prefix_skip_message} Skipped the current song.")
    else:
        await interaction.followup.send("There is no song currently playing to skip.")

@bot.tree.command(name="pause", description="Pause the song currently playing.")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if bot is in voice channel
    if voice_client is None:
        return await interaction.response.send_message("I'm not connected to a voice channel.")
    
    # Check if there is a song playing
    if not voice_client.is_playing():
        return await interaction.response.send_message("There is no song currently playing to pause.")
    
    # Pause the song
    voice_client.pause()
    print(f"Paused: is_playing={voice_client.is_playing()}, is_paused={voice_client.is_paused()}")
    print(SONG_QUEUES[str(interaction.guild.id)])

    random_pause_paths = [r"bin\voicelines\luna_snow_pause1.mp3", r"bin\voicelines\luna_snow_pause2.mp3"]
    pause_audio_path = random.choice(random_pause_paths)
    if pause_audio_path == r"bin\voicelines\luna_snow_pause1.mp3":
        prefix_pause_message = "POW! You're frozen!"
    else:
        prefix_pause_message = "A nice deep freeze!"
    await interaction.response.send_message(f"{prefix_pause_message} Paused the current song.")
    #await play_pause_voiceline(voice_client, pause_audio_path)

@bot.tree.command(name="resume", description="Resume the song currently paused.")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if bot is in a voice channel
    if voice_client is None:
        return await interaction.response.send_message("I'm not connected to a voice channel.")
    
    if voice_client.source is None:
        return await interaction.response.send_message("There is no audio source loaded to resume.")

    # Check if there is a song paused
    if not voice_client.is_paused():
        return await interaction.response.send_message("There is no song currently paused to resume.")
    
    print(f"Resuming: is_playing={voice_client.is_playing()}, is_paused={voice_client.is_paused()}")
    

    # Resume the song
    prefix_resume_message = random.choice(["I've still got songs to sing!", "I'm making a comeback!", "I'm back in the fight!"])
    voice_client.resume()
    await interaction.response.send_message(f"{prefix_resume_message} Resumed the current song.")

@bot.tree.command(name="stop", description="Stop the song currently playing and clear the queue.")
async def stop(interaction: discord.Interaction):
    await interaction.response.defer()
    voice_client = interaction.guild.voice_client

    # Check if the bot is in a voice channel
    if not voice_client or not voice_client.is_connected():
        return await interaction.followup.send("I'm not connected to a voice channel.")

    # Clear the server queue
    guild_id_str = str(interaction.guild.id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()
    
    # Check if there is a song playing or paused and stop it
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    random_exit_paths = [r"bin\voicelines\luna_snow_exit.mp3", r"bin\voicelines\luna_snow_exit2.mp3"]
    exit_audio_path = random.choice(random_exit_paths)
    await add_to_queue(guild_id_str, exit_audio_path, "Exit Voiceline", is_voiceline=True)
    duration = get_audio_duration(exit_audio_path)
    try:
        await play_next_song(voice_client, guild_id_str, interaction.channel)
        await asyncio.sleep(duration)
    except Exception as e:
        print(f"Error playing exit voiceline: {e}")

    # Disconnect the bot from voice channel
    await voice_client.disconnect()
    if exit_audio_path==r"bin\voicelines\luna_snow_exit.mp3":
        exit_message = "Exit. Stage Left."
    else:
        exit_message = "Bye-bye!"
    await interaction.followup.send(exit_message)

@bot.tree.command(name="queue", description="View the current song queue.")
async def show_queue(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_id = str(interaction.guild.id)

    if guild_id not in SONG_QUEUES or not SONG_QUEUES[guild_id]:
        print(f"No queue found for guild {guild_id}.")
        return await interaction.followup.send("The queue is currently empty.")
    
     # Debug: Log the queue content
    print(f"Queue for guild {guild_id}: {SONG_QUEUES[guild_id]}")
    
    embed = Embed(title="❄️ Current Song Queue ❄️", color=0xADD8E6)
    try:
        for index, song in enumerate(SONG_QUEUES[guild_id], start=1):
                title = song[1]
                embed.add_field(name="\u200b", value=f"**{index}.** {title}", inline=False)

    except Exception as e:
        print(f"Error while building embed: {e}")
        return await interaction.followup.send("An error occurred while retrieving the queue.")
    
    return await interaction.followup.send(embed=embed)
async def play_next_song(voice_client, guild_id, channel):

    if guild_id not in SONG_QUEUES or not SONG_QUEUES[guild_id]:
        print(f"No songs in queue to play.")
        return
    
    """
    print(f"[DEBUG] Voice client status for guild {guild_id}: "
          f"is_playing={voice_client.is_playing()}, "
          f"is_paused={voice_client.is_paused()}, "
          f"is_connected={voice_client.is_connected()}")
    """
    # Check if bot is already playing a song
    if voice_client.is_playing() or voice_client.is_paused():
        print("A song is already playing, waiting for it to finish.")
        return
    
    #print(SONG_QUEUES[guild_id])
    # Fetch next song in queue
    audio_url, title, is_voiceline = SONG_QUEUES[guild_id].popleft()

    try:
        if is_voiceline:
            source = discord.FFmpegPCMAudio(audio_url, executable=r"bin\ffmpeg\ffmpeg.exe")
        else:
            # Check if the URL is a valid m3u playlist
            m3u_urls = parse_m3u(audio_url)
            if m3u_urls:
                audio_url = m3u_urls[0]

            before_options = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -headers "User-Agent: Mozilla/5.0 (compatible; DiscordBot/1.0)\\r\\nReferer: https://soundcloud.com\\r\\n"'
            ffmpeg_options = {
                "before_options": before_options,
                "options": "-vn",
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)",
                "Referer": "https://soundcloud.com"
            }
            # Create audio source
            try:
                source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options, executable=r"bin\ffmpeg\ffmpeg.exe")
            except Exception:
                source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options, executable=r"bin\ffmpeg\ffmpeg.exe")
        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")   
            coro = play_next_song(voice_client, guild_id, channel)
            asyncio.run_coroutine_threadsafe(coro, bot.loop)

        # Play audio
        voice_client.play(source, after=after_play)

        print(f"Now playing: {title}")
    except Exception as e:
        print(f"Failed to play {title}: {e}")
        prefix_exception_message = random.choice(["I'm not at my best.", "I'm not doing too well.", "I'm still warming up.", "Not ready to perform quite yet."])
        await channel.send(f"{prefix_exception_message} Could not play **{title}**, Skipping...")
        # Attempt to play next song in queue
        await play_next_song(voice_client, guild_id, channel)

def get_queue_lock(guild_id):
    if guild_id not in QUEUE_LOCKS:
        QUEUE_LOCKS[guild_id] = Lock()
    return QUEUE_LOCKS[guild_id]

async def add_to_queue(guild_id, audio_url, title, is_voiceline=False, prepend=False):
    async with get_queue_lock(guild_id):
        if guild_id not in SONG_QUEUES:
            SONG_QUEUES[guild_id] = deque()
        if prepend:
            SONG_QUEUES[guild_id].appendleft((audio_url, title, is_voiceline))
        else:
            SONG_QUEUES[guild_id].append((audio_url, title, is_voiceline))
        print(f"[DEBUG] Updated SONG_QUEUES: {SONG_QUEUES[guild_id]}")

def get_audio_duration(file_path):
    """Get duration of an audio file using ffprobe."""
    try:
        result = subprocess.run(
            [
                r"bin\ffmpeg\ffprobe.exe", 
                "-i", file_path, 
                "-show_entries", "format=duration",
                "-v", "quiet",
                "-of", "json"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        duration = float(json.loads(result.stdout)["format"]["duration"])
        return duration
    except Exception as e:
        print(f"Error fetching duration for {file_path}: {e}")
        return 0 # Default duration if error occurs
    
def parse_m3u(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        lines = response.text.splitlines()
        stream_urls = [line for line in lines if not line.startswith("#") and line.strip()]
        return stream_urls
    except Exception as e:
        print(f"Failed to parse .m3u: {e}")
        return []
bot.run(TOKEN)
