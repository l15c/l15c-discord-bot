import discord
from discord.ext import commands
import asyncio

class ClearMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='clearMessage',aliases=['clm'], description='Xóa tin nhắn trong kênh chat.')
    @commands.has_permissions(administrator=True)
    async def clearMessage_(self,ctx, number):
        channel = ctx.channel
        number = int(number)
        counter = 0
        async for x in channel.history(limit=number):
            if counter < number:
                await discord.Message.delete(x)
                counter += 1
                await asyncio.sleep(0.5)

def setup(bot):
    bot.add_cog(ClearMessage(bot))