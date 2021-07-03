from discord.ext import commands,tasks
from random import choice
import discord
from os import getenv

bot = commands.Bot(command_prefix='#')
bot.load_extension("cogs.musicCog")
#bot.load_extension("cogs.cleanCog")
bot.load_extension("cogs.voiceChannelCog")

status = ['Player Unknown\'s Battlegrounds (PUBG)',
          'League of Legends',
          'Call of Duty: Warzone',
          'Business Tour',
          'Sea of Thieves',
          'Grand Theft Auto V',
          'Trần Quang Nhựt',
          'Trần Đỗ Việt Hoàng',]



@bot.event
async def on_ready():
    change_status.start()
    print("BOT is online!")
@tasks.loop(seconds=60)
async def change_status():
    await bot.change_presence(activity=discord.Game(choice(status)))


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(title="ERROR",
                              description="Lệnh không hợp lệ",
                              color=discord.Color.from_rgb(249,244,0))
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRole):
        embed = discord.Embed(title="WARNING",
                            description="Bạn không có quyền truy cập lệnh này",
                             color=discord.Color.red())
        await ctx.send(embed=embed)

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.channels, name='welcome')
    await channel.send(f'Chào mừng {member.mention} gia nhập làng!!! Gõ lệnh `!help` để biết thêm chi tiết!')

@bot.command(name='ping', help='Lệnh trả về độ trễ')
async def ping(ctx):
    await ctx.send(f'**Pong!** Ping: {round(bot.latency * 1000)}ms')



bot.run(getenv('TOKEN'))
