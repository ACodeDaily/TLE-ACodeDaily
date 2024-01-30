from discord.ext import commands
import discord
import logging
import google.generativeai as genai
from tle.util import gemini_model_settings as settings
import requests
from PIL import Image
from tle import constants
from ratelimit import limits, sleep_and_retry



ONE_MINUTE = 60
MAX_CALLS_PER_MINUTE = 60
GEMINI_API_KEY = constants.GEMINI_API_KEY

IMAGE_TYPES = ["jpeg", "png", "webp", "heic", "heif"]
NO_RESPONSE_MESSAGE = "Sorry, can't answer that. possible reasons might be no response, recitation, safety issue or blocked content."
HELP_TEXT = "```\nUsage:\n$chat : to create a public thread to interact with the bot.\n$private : to create a private thread to interact with the bot.\n\nACD AI answers to all text, image and attachment.\nHave fun!\n\nfor Admin/Mods:\n$set : to set a channel.\n$unset : to unset a channel.\n$show : to show current channels.\n$clear : to delete all the threads in set channels.```"
ALLOWED_GUILDS = [1063393625049923687, 501032525284769842]
DEV_ID = 501026469569363988
logger = logging.getLogger(__name__)

class ACD_AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        '''ids of text channels which will be used for opening chat threads with ai'''
        self.allowed_channels: list = []
        
        '''for restricting use to only certain discord servers'''
        self.allowed_guilds: list = ALLOWED_GUILDS
        
        '''developer's discord user id (vedantmishra69)'''
        self.dev_id: int = DEV_ID
        
        genai.configure(api_key=GEMINI_API_KEY)
        
        '''gemini model for text inputs'''
        self.text_model = genai.GenerativeModel(model_name="gemini-pro",
                              generation_config=settings.text_generation_config, 
                              safety_settings=settings.text_safety_settings)
        
        '''gemini model for image inputs'''
        self.image_model = genai.GenerativeModel(model_name="gemini-pro-vision",
                              generation_config=settings.image_generation_config, 
                              safety_settings=settings.image_safety_settings)
        
        '''to store chat session instances for each opened thread (thread_id: chat_session)'''
        self.chats: dict = {}
        
    async def print_response(self, response, message):
        '''prints the response to thread channel recieved from get_response()'''
        async with message.channel.typing():
            strings = []
            for index in range(0, len(response), 2000):
                strings.append(response[index: min(len(response), index + 2000)])
            try:
                await message.reply(strings[0])
                for string in strings[1:]:
                    await message.channel.send(string)
            except Exception as e:
                message.reply("No response, discord issue :(")
                logger.warn(f"last message: {message.content}\n{e}".format())
    
    @sleep_and_retry
    @limits(calls=MAX_CALLS_PER_MINUTE, period=ONE_MINUTE)
    async def get_response(self, message, chat):
        '''
        takes message object and chat session instance
        sends the message content (text/image) to gemini model
        sends the response recieved from gemini to print_response()
        '''
        async with message.channel.typing():
            image = None
            response = ""
            attachment = message.attachments[0] if message.attachments else None
            if not attachment:
                try:
                    response = chat.send_message(message.content).text
                except Exception as e:
                    response = NO_RESPONSE_MESSAGE
                    logger.warn(f"last message: {message.content}\n{e}".format())
            elif attachment.content_type.split('/')[0] == "image":
                if attachment.content_type.split('/')[1] in IMAGE_TYPES:
                    try:
                        image = Image.open(requests.get(attachment.url, stream = True).raw)
                        response = self.image_model.generate_content([message.content, image] if message.content else image).text
                    except Exception as e:
                        response = "Unable to process that image."
                        logger.warn(f"last message: {attachment.url}\n{e}".format())
                else: response = "Invalid image format. please use JPEG, PNG, WEBP, HEIC or HEIF"
            else:
                try:
                    att_content = requests.get(attachment.url).content.decode()
                except Exception as e:
                    response = "Format not supported: " + attachment.filename
                    logger.warn(f"last message: {attachment.url}\n{e}".format())
                else:
                    try:
                        response = chat.send_message(message.content + '\n\n' + att_content)
                    except Exception as e:
                        response = NO_RESPONSE_MESSAGE
        self.bot.loop.create_task(self.print_response(response, message))
    
    def has_permissions(self, message):
        '''
        returns True if the command is coming from the developer
        but if the user is not the developer 
        it check whether they have "manage_channels" permission
        and it is coming from an unrestrcited discord server
        '''
        return (message.author.guild_permissions.manage_channels and message.guild.id in self.allowed_guilds) or message.author.id == self.dev_id
    
    async def start_thread(self, message, is_public):
        '''starts a thread on $chat or $private commands'''
        try:
            thread = await message.channel.create_thread(name = "Session with " + message.author.name, slowmode_delay = 1, auto_archive_duration = 60, message = message if is_public else None)
            await thread.add_user(message.author)
            hello_text = self.text_model.generate_content("hi").text
            async with thread.typing():
                await thread.send(content = f'<@{message.author.id}> {hello_text}')
            self.chats[str(thread.id)] = self.text_model.start_chat(history=[{'role':'user', 'parts': ["hi"]}, {'role': 'model', 'parts': [hello_text]}])
        except Exception as e:
            await message.channel.send("Could not start a thread :(")
            logger.warn(e)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        
        '''shows currently added text channels in the server for ai use'''
        if message.content.startswith("$show"):
            if self.has_permissions(message):
                set_channels = []
                channel_count = 1
                for Id in self.allowed_channels:
                    if message.guild.get_channel(Id):
                        set_channels.append(f"\n{channel_count}. {message.guild.get_channel(Id).name}")
                        channel_count += 1
                if set_channels:
                    await message.channel.send("Current channels:" + "".join(set_channels))
                else:
                    await message.channel.send("No channel has been set. type $set to set it.")
            else:
                await message.channel.send("you don't have ``Manage channels`` permission!")

        '''sets a text channel for ai use'''
        if message.content.startswith("$set"):
            if self.has_permissions(message):
                if message.channel.type == discord.ChannelType.text:
                    if message.channel.id not in self.allowed_channels:
                        self.allowed_channels.append(message.channel.id)
                        await message.channel.send(f"channel ``{message.channel.name}`` has been set successfully.")
                    else:
                        await message.channel.send(f"``{message.channel.name}`` is already set.")
                else:
                    await message.channel.send("It should be a text channel!")
            else:
                await message.channel.send("you don't have ``Manage channels`` permission!")

        '''shows all working commands for ai feature'''
        if message.content.startswith("$help"):
            await message.channel.send(HELP_TEXT)

        '''unsets a text channel for ai use'''
        if message.content.startswith("$unset"):
            if self.has_permissions(message):
                if message.channel.id in self.allowed_channels:
                    self.allowed_channels.remove(message.channel.id)
                    await message.channel.send(f"channel ``{message.channel.name}`` has been unset successfully.")
                else:
                    await message.channel.send("This channel has not been set. type $set to set it.")
            else:
                await message.channel.send("you don't have ``Manage channel`` permission!")

        '''deletes all active chat threads'''
        if message.content.startswith("$clear"):
            if message.author.guild_permissions.manage_threads:
                for Id in self.allowed_channels:
                    if message.guild.get_channel(Id):
                        thread_count = 0
                        async with message.channel.typing():
                            for thread in message.guild.get_channel(Id).threads:
                                await thread.delete()
                                thread_count += 1
                        await message.channel.send(f"{thread_count} threads deleted for ``{message.guild.get_channel(Id).name}``.")
            else:
                await message.channel.send("you don't have ``Manage threads`` permission!")

        '''
        sends user's input for processing to gemini 
        or starts a new chat thread with $chat or $private command
        '''
        if str(message.channel.id) in self.chats:
            self.bot.loop.create_task(self.get_response(message, self.chats[str(message.channel.id)]))
        elif message.content:
            first = message.content.split()[0]
            if first == "$chat":
                if message.channel.id in self.allowed_channels:
                    await self.start_thread(message, True)
                else:
                    await message.channel.send("This channel has not been set. type $set to set it.")
            elif first == "$private":
                if message.channel.id in self.allowed_channels:
                    await self.start_thread(message, False)
                else:
                    await message.channel.send("This channel has not been set. type $set to set it.")

async def setup(bot):
    await bot.add_cog(ACD_AI(bot))