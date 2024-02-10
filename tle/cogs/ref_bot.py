import json
import requests
from discord.ext import commands
from tle.util import discord_common
import logging
from tle.util import codeforces_common as cf_common
from tle import constants

logger = logging.getLogger(__name__)
RATING_LIMIT = 1500

class ReferralBotCogError(commands.CommandError):
    pass

class ReferralBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.url = "https://ref-portal-indol.vercel.app/api/secret?cfUserName={cf_handle}&discordId={discord_id}"
        self.converter = commands.MemberConverter()
    
    @commands.group(brief='Referral bot',
                    invoke_without_command=True)
    @cf_common.user_guard(group='ref')
    async def ref(self,ctx,*args):
        """
        Submits request for referral on ref portal.
        """
        await ctx.send_help(ctx.command)
        
    @ref.command(brief='gets channel for referral request.')
    async def get_channel(self, ctx):
        """
        Gets channel to be used for requesting referral form.
        """
        channel_id = cf_common.user_db.get_ref_channel(ctx.guild.id)
        if not channel_id:
            raise ReferralBotCogError('There is no referral channel. Set one with ``;ref set_channel``.')
        await ctx.send(embed=discord_common.embed_success(f"Current referral channel: <#{channel_id}>"))
    
    @ref.command(brief='sets channel for referral request.')
    @commands.has_any_role(constants.TLE_ADMIN, constants.TLE_MODERATOR)    
    async def set_channel(self, ctx):
        """
        Sets channel to be used for requesting referral form.
        """
        cf_common.user_db.set_ref_channel(ctx.guild.id, ctx.channel.id)
        await ctx.send(embed=discord_common.embed_success('Referral channel saved successfully'))
    
    @ref.command(brief='requests referral form.')
    @cf_common.user_guard(group='ref')
    async def get(self, ctx):
        """
        Requests referral form from the ref portal.
        """
        channel_id = cf_common.user_db.get_ref_channel(ctx.guild.id)
        if not channel_id:
            raise ReferralBotCogError('There is no referral channel. Set one with ``;ref set_channel``.')
        if ctx.channel.id != channel_id:
            raise ReferralBotCogError(f"You must use this command in referral channel: <#{channel_id}>")
        cf_handle, = await cf_common.resolve_handles(ctx, self.converter, ('!' + str(ctx.author.id),))
        discord_id = ctx.author.name
        url = self.url.format(cf_handle=cf_handle, discord_id=discord_id)
        user = cf_common.user_db.fetch_cf_user(cf_handle)
        if user.maxRating < RATING_LIMIT:
            await ctx.reply(embed=discord_common.embed_alert(f"You need to have your maximum codeforces rating >= {RATING_LIMIT}."))
        else:
            dm_channel = await ctx.author.create_dm()
            payload = {
                "secretKey": "6QGMP4QD8amDPnTBC3Tfwo8L4Ckny4Cl",
                "secretAccessKey": "M4MICU67LFq5UH2NLaLSgbOaRBjliuO5"
            }
            try:
                response = json.loads(requests.get(url, headers=payload).text)
                if "url" in response:
                    res = response["url"]
                    await dm_channel.send(embed=discord_common.embed_success(f"Here is your referral form link: {res}\n\nPlease note that entering an **invalid job id** may result in your **banishment** from the server."))
                    await ctx.reply(embed=discord_common.embed_success("Sent!"))
                else: await dm_channel.send(embed=discord_common.embed_alert("No URL available."))
            except Exception as e:
                ctx.reply(embed=discord_common.embed_alert("No response from the server."))
                logger.warn(e)
                
    @discord_common.send_error_if(ReferralBotCogError, cf_common.ResolveHandleError,
                                  cf_common.FilterError)
    async def cog_command_error(self, ctx, error):
        pass           
    
        

async def setup(bot):
    await bot.add_cog(ReferralBot(bot))
        