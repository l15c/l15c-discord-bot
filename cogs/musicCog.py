import discord
from discord.ext import commands
import random
import asyncio
import itertools
import sys
import traceback
from async_timeout import timeout
from functools import partial
import youtube_dl
from youtube_dl import YoutubeDL

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdlopts = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # ipv6 addresses cause issues sometimes
}

ffmpegopts = {
    'before_options': '-nostdin',
    'options': '-vn'
}

ytdl = YoutubeDL(ytdlopts)


class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""


class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""


class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, requester):
        super().__init__(source)
        self.requester = requester

        self.title = data.get('title')
        self.web_url = data.get('webpage_url')
        self.duration = data.get('duration')


    def __getitem__(self, item: str):
        """Allows us to access attributes similar to a dict.
                This is only useful when you are NOT downloading.
                """
        """Cho phép chúng tôi truy cập các thuộc tính tương tự như một dict.
            Điều này chỉ hữu ích khi bạn KHÔNG tải xuống.
        """
        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        embed = discord.Embed(title="",
                              description=f"[{data['title']}]({data['webpage_url']})",
                              color=discord.Color.green())
        embed = embed.set_author(name=f"{ctx.author.display_name} đã thêm 1 bài hát",icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)

        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {'webpage_url': data['webpage_url'], 'requester': ctx.author, 'title': data['title']}

        return cls(discord.FFmpegPCMAudio(source), data=data, requester=ctx.author)

    @classmethod
    async def regather_stream(cls, data, *, loop):
        """Used for preparing a stream, instead of downloading.
        Since Youtube Streaming links expire."""
        """Được sử dụng để chuẩn bị một luồng, thay vì tải xuống.
        Kể từ khi liên kết phát trực tuyến trên Youtube hết hạn."""
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']

        to_run = partial(ytdl.extract_info, url=data['webpage_url'], download=False)
        data = await loop.run_in_executor(None, to_run)

        return cls(discord.FFmpegPCMAudio(data['url']), data=data, requester=requester)


class MusicPlayer:
    """A class which is assigned to each guild using the bot for Music.
    This class implements a queue and loop, which allows for different guilds to listen to different playlists
    simultaneously.
    When the bot disconnects from the Voice it's instance will be destroyed.
    """

    __slots__ = ('bot', '_guild', '_channel', '_cog', 'queue', 'next', 'current', 'np', 'volume')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None  # Now playing message
        self.volume = 1.0
        self.current = None

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        """Our main player loop."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                # Wait for the next song. If we timeout cancel the player and disconnect...
                async with timeout(600):  # 5 minutes...
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                return self.destroy(self._guild)

            if not isinstance(source, YTDLSource):
                # Source was probably a stream (not downloaded)
                # So we should regather to prevent stream expiration
                try:
                    source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                except Exception as e:
                    await self._channel.send(f'Đã xảy ra lỗi khi xử lý bài hát.\n'
                                             f'```css\n[{e}]\n```')
                    continue

            source.volume = self.volume
            self.current = source

            self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            embed = discord.Embed(title="Đang phát",
                                  description=f"[{source.title}]({source.web_url})",
                                  color=discord.Color.green())
            embed = embed.set_footer(text=f'Requested by {source.requester.display_name}',icon_url=source.requester.avatar_url)
            self.np = await self._channel.send(embed=embed)
            await self.next.wait()

            # Make sure the FFmpeg process is cleaned up.
            source.cleanup()
            self.current = None

    def destroy(self, guild):
        """Disconnect and cleanup the player."""
        return self.bot.loop.create_task(self._cog.cleanup(guild))


class Music(commands.Cog):
    """Music related commands."""

    __slots__ = ('bot', 'players')

    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    async def cleanup(self, guild):
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass

        try:
            del self.players[guild.id]
        except KeyError:
            pass

    async def __local_check(self, ctx):
        """A local check which applies to all commands in this cog."""
        if not ctx.guild:
            raise commands.NoPrivateMessage
        return True

    async def __error(self, ctx, error):
        """A local error handler for all errors arising from commands in this cog."""
        if isinstance(error, commands.NoPrivateMessage):
            try:
                return await ctx.send('Không thể sử dụng lệnh này trong TIN NHẮN RIÊNG')
            except discord.HTTPException:
                pass
        elif isinstance(error, InvalidVoiceChannel):
            await ctx.send('Lỗi kết nối đến kênh thoại. '
                           'Đảm bảo rằng bạn đang ở trong một kênh hợp lệ hoặc gõ vào một kênh')

        print('Bỏ qua ngoại lệ trong lệnh {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    def get_player(self, ctx):
        """Retrieve the guild player, or generate one."""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player

        return player

    @commands.command(name='join', aliases=['connect', 'j'], description="Kết nối vào kênh thoại.")
    async def connect_(self, ctx, *, channel: discord.VoiceChannel = None):
        """Kết nối vào kênh thoại

        Thông số
        ------------
        <channel>: Tên kênh thoại [Tùy chọn]
            The channel to connect to. If a channel is not specified, an attempt to join the voice channel you are in
            will be made.
            Kênh để trình phát kết nối. Nếu không được chỉ định, trình phát sẽ tham gia vào kênh thoại mà bạn đang tham gia.
        Lệnh này có thể dùng để di chuyển BOT sang các kênh khác nhau.
        """

        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                embed = discord.Embed(title="",
                                      description="Chưa chỉ định kênh. Vui lòng gõ `!join` từ kênh thoại.",
                                      color=discord.Color.green())
                await ctx.send(embed=embed)
                raise InvalidVoiceChannel('Chưa chỉ định kênh. Vui lòng chỉ định hoặc tham gia kênh thoại.')

        vc = ctx.voice_client

        if vc:
            if vc.channel.id == channel.id:
                return
            try:
                await vc.move_to(channel)
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f'Chuyển sang kênh: <{channel}> (timed out).')
        else:
            try:
                await channel.connect()
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f'Kết nối tới kênh: <{channel}> (timed out).')
        if (random.randint(0, 1) == 0):
            await ctx.message.add_reaction('👍')
        await ctx.send(f'**Đã kết nối `{channel}`**')

    @commands.command(name='play', aliases=['sing', 'p'], description="Phát nhạc hoặc thêm vào hàng chờ.")
    async def play_(self, ctx, *, search: str):
        """Phát nhạc hoặc thêm vào hàng chờ.
        Lệnh này sẽ kết nối BOT vào một kênh thoại hợp lệ nếu BOT chưa kết nối.
        Sử dụng YTDL để tự động tìm kiếm và truy xuất 1 bài hát.

        Thông số
        ------------
        <search>: str [bắt buộc]
            Bài hát được tìm kiếm và truy xuất bằng YTDL. Đây có thể là một tên một bài hát, ID hoặc URL.
        """

        if not search:
            embed = discord.Embed(title="", description="Nhập vào tên bài hát hoặc URL",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)
        await ctx.trigger_typing()

        vc = ctx.voice_client

        if not vc:
            await ctx.invoke(self.connect_)

        player = self.get_player(ctx)

        # If download is False, source will be a dict which will be used later to regather the stream.
        # If download is True, source will be a discord.FFmpegPCMAudio with a VolumeTransformer.
        source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop, download=False)

        await player.queue.put(source)

    @commands.command(name='pause', description="Tạm dừng.")
    async def pause_(self, ctx):
        """Tạm dừng."""

        vc = ctx.voice_client

        if not vc or not vc.is_playing():
            embed = discord.Embed(title="", description="Trình phát không có nhạc",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)
        elif vc.is_paused():
            embed = discord.Embed(title="", description="Trình phát đang tạm dừng.",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        vc.pause()
        await ctx.send("Tạm dừng ⏸️")

    @commands.command(name='resume', description="Tiếp tục phát nhạc.")
    async def resume_(self, ctx):
        """Tiếp tục phát nhạc."""

        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            embed = discord.Embed(title="", description="Trình phát không có kết nối",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)
        elif not vc.is_paused():
            embed = discord.Embed(title="",description="Trình phát đang phát nhạc.",
                                  color=discord.Color.green())
            return  await ctx.send(embed=embed)

        vc.resume()
        await ctx.send("Tiếp tục phát ▶️")

    @commands.command(name='skip', description="Phát bài hát tiếp theo trong hàng đợi.")
    async def skip_(self, ctx):
        """Phát bài hát tiếp theo."""

        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            embed = discord.Embed(title="", description="Trình phát không có kết nối",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        if vc.is_paused():
            pass
        elif not vc.is_playing():
            return

        vc.stop()

    @commands.command(name='remove', aliases=['rm', 'rem'], description="Xóa bài hát được chỉ định khỏi hàng chờ.")
    async def remove_(self, ctx, pos: int = None):
        """Xóa bài hát được chỉ định khỏi hàng chờ."""

        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            embed = discord.Embed(title="", description="Trình phát không có kết nối",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        player = self.get_player(ctx)
        if pos == None:
            player.queue._queue.pop()
        else:
            try:
                s = player.queue._queue[pos - 1]
                del player.queue._queue[pos - 1]
                embed = discord.Embed(title="",
                                      description=f"Đã xóa [{s['title']}]({s['webpage_url']}) [{s['requester'].mention}]",
                                      color=discord.Color.green())
                await ctx.send(embed=embed)
            except:
                embed = discord.Embed(title="", description=f'Không tìm thấy nhạc tại "{pos}"',
                                      color=discord.Color.green())
                await ctx.send(embed=embed)

    @commands.command(name='clear', aliases=['clr', 'cl', 'cr'], description="Xóa toàn bộ hàng chờ.")
    async def clear_(self, ctx):
        """Xóa toàn bộ hàng chờ."""

        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            embed = discord.Embed(title="", description="Trình phát không có kết nối",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        player = self.get_player(ctx)
        player.queue._queue.clear()
        await ctx.send('🧹 **Đã xóa hàng chờ**')

    @commands.command(name='queue', aliases=['q', 'playlist', 'que'], description="Hiển thị hàng chờ.")
    async def queue_info(self, ctx):
        """Hiển thị hàng chờ."""

        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            embed = discord.Embed(title="", description="Trình phát không có kết nối",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        player = self.get_player(ctx)
        if player.queue.empty():
            embed = discord.Embed(title="", description="Hàng chờ trống", color=discord.Color.green())
            return await ctx.send(embed=embed)

        seconds = vc.source.duration % (24 * 3600)
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        if hour > 0:
            duration = "%dh %02dm %02ds" % (hour, minutes, seconds)
        else:
            duration = "%02dm %02ds" % (minutes, seconds)

        # Grabs the songs in the queue...
        upcoming = list(itertools.islice(player.queue._queue, 0, int(len(player.queue._queue))))
        fmt = '\n'.join(
            f"`{(upcoming.index(_)) + 1}.` [{_['title']}]({_['webpage_url']}) | ` {duration} ` \n`Requested by: {_['requester'].display_name} `\n"
            for _ in upcoming)
        fmt = f"\n__Đang phát__:\n[{vc.source.title}]({vc.source.web_url}) | ` {duration} `\n` Requested by: {vc.source.requester.display_name} `\n\n__Tiếp theo:__\n" + fmt + f"\n**{len(upcoming)} bài hát trong hàng chờ**"
        embed = discord.Embed(title=f'Trình phát nhạc {self.bot.user.name}', description=fmt, color=discord.Color.green())


        await ctx.send(embed=embed)

    @commands.command(name='np', aliases=['song', 'current', 'currentsong', 'playing'],
                      description="Hiện thông tin bài hát đang phát.")
    async def now_playing_(self, ctx):
        """Hiện thông tin bài hát đang phát."""

        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            embed = discord.Embed(title="", description="Trình phát không có kết nối",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        player = self.get_player(ctx)
        if not player.current:
            embed = discord.Embed(title="", description="Trình phát không có nhạc.",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        seconds = vc.source.duration % (24 * 3600)
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        if hour > 0:
            duration = "%dh %02dm %02ds" % (hour, minutes, seconds)
        else:
            duration = "%02dm %02ds" % (minutes, seconds)

        embed = discord.Embed(title="",
                              description=f"[{vc.source.title}]({vc.source.web_url})|` {duration} `",
                              color=discord.Color.green())
        embed.set_author(icon_url=self.bot.user.avatar_url, name=f"Đang phát nhạc 🎶🎶")
        embed.set_footer(text=f'Requested by {vc.source.requester.display_name}', icon_url=vc.source.requester.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(name='volume', aliases=['vol', 'v'], description="Điều chỉnh âm lượng.")
    async def change_volume(self, ctx, *, vol: float = None):
        """Điều chỉnh âm lượng.

        Thông số
        ------------
        <volume>: Số thực hoặc số nguyên [bắt buộc]
            Âm lượng trình phát sẽ được đặt theo %. Nằm trong khoảng [1-100].
        """
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            embed = discord.Embed(title="", description="Trình phát không có kết nối",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        if not vol:
            embed = discord.Embed(title="", description=f"🔊 **{vc.source.volume * 100}%**",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        if not 0 < vol < 101:
            embed = discord.Embed(title="", description="Vui lòng chọn giá trị từ 1 đến 100",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        player = self.get_player(ctx)

        if vc.source:
            vc.source.volume = vol / 100

        player.volume = vol / 100
        embed = discord.Embed(title="", description=f'**`{ctx.author}`** Thiết lập mức âm lượng **{vol}%**',
                              color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command(name='leave', aliases=["stop", "dc", "disconnect", "bye"],
                      description="Ngừng phát và ngắt kết nối khỏi kênh thoại.")
    async def leave_(self, ctx):
        """Ngừng phát và ngắt kết nối khỏi kênh thoại.

        !CẢNH BÁO!
            Điều này sẽ ngắt kết nối trình phát nhạc, mọi cài đặt và hàng đợi sẽ bị xóa.
        """
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            embed = discord.Embed(title="", description="Trình phát không có kết nối",
                                  color=discord.Color.green())
            return await ctx.send(embed=embed)

        if 0 == random.randint(0, 1):
            await ctx.message.add_reaction('👋')
        await ctx.send('**Ngắt kết nối**')

        await self.cleanup(ctx.guild)


def setup(bot):
    bot.add_cog(Music(bot))






