import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
from collections import deque
import re
import random

load_dotenv()
TOKEN= os.getenv("DISCORD_TOKEN")
YOUTUBE_URL_REGEX = r"(https)?://(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/embed/)?[^\s&]+"
SONG_QUEUES = {}

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

async def play_join_voiceline(voice_client):
    random_join_paths = [r"bin\voicelines\luna_snow_join1.mp3",r"bin\voicelines\luna_snow_join2.mp3", r"bin\voicelines\luna_snow_join3.mp3"]
    join_audio_path = random.choice(random_join_paths)

    source = source = discord.FFmpegPCMAudio(join_audio_path, executable=r"bin\ffmpeg\ffmpeg.exe")
    voice_client.play(source)

async def play_ult(voice_client, guild_id, channel, next_audio_url, next_title):
    random_ult_paths = [r"bin\voicelines\luna_snow_ult.mp3", r"bin\voicelines\Luna_snow_ult_friendly.mp3"]
    ult_audio_path = random.choice(random_ult_paths)

    def after_join_play(error):
        if error:
            print(f"Error playing join sound: {error}")
        
        # After ult sound, play requested song
        if not voice_client.is_playing():
            coro = play_next_song(voice_client, guild_id, channel)
            asyncio.run_coroutine_threadsafe(coro, bot.loop)

    # Play ult sound first
    source = discord.FFmpegPCMAudio(ult_audio_path, executable=r"bin\ffmpeg\ffmpeg.exe")
    voice_client.play(source, after=after_join_play)

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
        await play_join_voiceline(voice_client)
    elif voice_client != voice_client.channel:
        await voice_client.move_to(voice_channel)
        await play_join_voiceline(voice_client)
    ydl_options = {
        "format": "bestaudio[ext=webm]/bestaudio/best",
        "noplaylist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
    }

    # Check if input query is a Youtube URL
    if re.match(YOUTUBE_URL_REGEX, song_query):
        youtube_url = song_query
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                track_info = ydl.extract_info(youtube_url, download=False)
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
            await interaction.followup.esnd("No results found for your query.")
            return
        
        first_track = tracks[0]
        audio_url = first_track["url"]
        title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    #Append song to the queue
    SONG_QUEUES[guild_id].append((audio_url, title))

    #Check if bot is already in voice channel playing a song
    if not voice_client.is_playing() and not voice_client.is_paused():
        #Play song immediately
        await interaction.followup.send(f"Now playing: **{title}**")
        await play_ult(voice_client, guild_id, interaction.channel, audio_url, title)
    else:
        #Tell user song was added to queue
        await interaction.followup.send(f"Added **{title}** to the queue.")

def add_to_queue(guild_id, audio_url, title, is_voiceline=False):
    if guild_id not in SONG_QUEUES:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title, is_voiceline))


@bot.tree.command(name="skip", description="Skip the current song.")
async def skip(interaction: discord.Interaction):
    await interaction.response.defer()
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        await interaction.response.send_message("Skipped the current song.")
    else:
        await interaction.response.send_message("There is no song currently playing to skip.")

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
    await interaction.response.send_message("Paused the current song.")

@bot.tree.command(name="resume", description="Resume the song currently paused.")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if bot is in a voice channel
    if voice_client is None:
        return await interaction.response.send_message("I'm not connected to a voice channel.")
    
    # Check if there is a song paused
    if not voice_client.is_paused():
        return await interaction.response.send_message("There is no song currently paused to resume.")
    
    # Resume the song
    voice_client.resume()
    await interaction.response.send_message("Resumed the current song.")

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
    if voice_client.is_playing or voice_client.is_paused():
        voice_client.stop()

    await interaction.followup.send("Stopped playback and disconnected.")

    # Disconnect the bot from voice channel
    await voice_client.disconnect()


async def play_next_song(voice_client, guild_id, channel):

    if guild_id not in SONG_QUEUES or not SONG_QUEUES[guild_id]:
        await channel.send("Exit. Stage left.")
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()
        return
    # Fetch next song in queue
    audio_url, title = SONG_QUEUES[guild_id].popleft()


    ffmpeg_options = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn",
    }
    try:    
        # Create audio source
        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options, executable=r"bin\ffmpeg\ffmpeg.exe")
        
        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")   
            coro = play_next_song(voice_client, guild_id, channel)
            asyncio.run_coroutine_threadsafe(coro, bot.loop)

        # PLay audio
        voice_client.play(source, after=after_play)
    except Exception as e:
        print(f"Failed to play {title}: {e}")
        await channel.send(f"Could not play **{title}**, Skipping...")
        # Attempt to play next song in queue
        await play_next_song(voice_client, guild_id, channel)

bot.run(TOKEN)
