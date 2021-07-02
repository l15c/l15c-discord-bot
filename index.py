import discord
from discord import guild
from discord.channel import VoiceChannel
from discord.ext import commands,tasks
import asyncio
import youtube_dl
import os

from random import choice

TOKEN = "ODU5Mzk3MzUwNjg5OTk2ODEw.YNsGJw.ACPAsF32Dk-TAogy7Dz70focwds"

youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.mp3',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=1.0):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


client = commands.Bot(command_prefix='!')

status = ['LoL!', 'Eating!', 'Sleeping!','GTA V']
queue = []

@client.event
async def on_ready():
    change_status.start()
    print("BOT is online!")

@client.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.channels, name='welcome')
    await channel.send(f'Welcome {member.mention}!  Ready to jam out? See `!help` command for details!')

@client.command(name='ping', help='Lệnh trả về độ trễ')
async def ping(ctx):
    await ctx.send(f'**Pong!** Ping: {round(client.latency * 1000)}ms')

@client.command(name='join', help='Lệnh gọi BOT vào kênh thoại')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("Bạn chưa kết nối với kênh thoại")
        return
    else:
        channel = ctx.message.author.voice.channel

    await channel.connect()

@client.command(name='queue', help='Thêm bài hát vào hàng chờ')
async def queue_(ctx, url):
    global queue

    queue.append(url)
    await ctx.send(f'`{url}` đã được thêm vào hàng chờ!')


@client.command(name='remove', help='Xóa bài hát khỏi hàng chờ')
async def remove(ctx, number):
    global queue

    try:
        del (queue[int(number-1)])
        temp = 1
        list = f'\nHàng chờ hiện tại của bạn:\n'
        for i in queue:
            show = await YTDLSource.from_url(i)
            list += f'{temp}.  {format(show.title)}\n'
            temp += 1
        await ctx.send(f'`{list}`')
    except:
        await ctx.send('Hàng chờ của bạn **trống** hoặc chỉ mục **nằm ngoài phạm vi hàng chờ**')

@client.command(name='play', help='Phát bài hát hoặc thêm vào hàng đợi.')
async def play(ctx,url = None):
    global queue

    if not ctx.message.author.voice:
        await ctx.send("Bạn chưa kết nối với kênh thoại")
        return
    else:
        channel = ctx.message.author.voice.channel
        voice = discord.utils.get(ctx.guild.voice_channels, name=channel.name)
        voice_client = discord.utils.get(client.voice_clients, guild=ctx.guild)
        if voice_client == None:
            await voice.connect()

    server = ctx.message.guild
    voice_channel = server.voice_client
    if url == None:
        if len(queue) == 0:
            await ctx.send('`Hàng chờ rỗng`')
            return
        if voice_channel.is_playing():
            await ctx.send('`Trình phát nhạc đang chạy...`')
        else:
            async with ctx.typing():
                player = await YTDLSource.from_url(queue[0], loop=client.loop)
                voice_channel.play(player, after=lambda e: print('Lỗi: %s' % e) if e else None)
            await ctx.send('**Đang phát:** {}'.format(player.title))
            del(queue[0])
    else:
        if voice_channel.is_playing():
            await ctx.send(f'`Trình phát nhạc đang chạy...\n``{url}`` đã được thêm vào hàng chờ')
            queue.append(url)
        else:
            async with ctx.typing():
                player = await YTDLSource.from_url(url, loop=client.loop)
                voice_channel.play(player, after=lambda e: print('Lỗi: %s' % e) if e else None)

            await ctx.send('**Đang phát:** {}'.format(player.title))

@client.command(name='pause', help='Tạm dừng')
async def pause(ctx):
    server = ctx.message.guild
    voice_channel = server.voice_client
    if voice_channel.is_playing():
        voice_channel.pause()
        await ctx.send('`Tạm dừng phát nhạc`')
    else:
        await ctx.send("`Nhạc đã được tạm dừng`")

@client.command(name='resume', help='Tiếp tục phát')
async def resume(ctx):
    server = ctx.message.guild
    voice_channel = server.voice_client

    if voice_channel.is_paused():
        voice_channel.resume()
        await ctx.send('`Tiếp tục phát nhạc...`')
    else:
        await ctx.send("Không có nhạc đang tạm dừng.")

@client.command(name='view', help='In hàng đợi')
async def view(ctx):
    if len(queue) == 0:
        await ctx.send('`Hàng đợi trống`')
    else:
        temp = 1
        list = f'\nHàng đợi hiện tại của bạn:\n'
        for i in queue:
            show = await YTDLSource.from_url(i)
            list += f'{temp}.  {format(show.title)}\n'
            temp += 1
        await ctx.send(f'`{list}`')


@client.command(name='leave', help='Ngắt kết nối BOT')
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        await voice_client.disconnect()
    else:
        await ctx.send("BOT không ở trong phòng.")

@client.command(name='stop', help='Dừng bài hát!')
async def stop(ctx):
    server = ctx.message.guild
    voice_channel = server.voice_client

    voice_channel.stop()


@client.command(name='next', help='Phát bài hát tiếp theo')
async def next(ctx):
    server = ctx.message.guild
    voice_channel = server.voice_client
    if len(queue) != 0:
        voice_channel.stop()
        async with ctx.typing():
            player = await YTDLSource.from_url(queue[0], loop=client.loop)
            voice_channel.play(player, after=lambda e: print('Lỗi: %s' % e) if e else None)
        await ctx.send('**Đang phát:** {}'.format(player.title))
        del (queue[0])
    else:
        await ctx.send('`Hàng đợi trống`')


@tasks.loop(seconds=20)
async def change_status():
    await client.change_presence(activity=discord.Game(choice(status)))

client.run(TOKEN)