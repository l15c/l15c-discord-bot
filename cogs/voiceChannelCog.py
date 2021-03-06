from discord.ext import commands

class Activities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        if after.channel is not None and before.channel is not None:
            if before.channel.id == after.channel.id:
                return

        if after.channel is not None:
            if after.channel.name == "🔑・tạo phòng":
                if before.channel is not None:
                    if before.channel.name != "🔑・tạo phòng" and len(before.channel.members) == 0:
                        await before.channel.delete()
                channel = await after.channel.category.create_voice_channel(f"{member.name}'s Room")
                return await  member.move_to(channel)
        else:
            if len(before.channel.members) == 0:
                return await before.channel.delete()

        if after.channel is not None and before.channel is not None:
            if (before.channel.name != "🔑・tạo phòng" and len(before.channel.members) == 0) and after.channel.name != "🔑・tạo phòng":
                await before.channel.delete()


def setup(bot):
    bot.add_cog(Activities(bot))
