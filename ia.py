#***********************************************************************************#
#                                   Modules/Imports                                 #
#***********************************************************************************#

# Async Imports
from __future__ import unicode_literals
import concurrent.futures
import asyncio

# Database Imports
import psycopg2
from constant_info import *

# Discord API
import discord
from discord.ext import commands

# Media Player and Downloader
from audioread import audio_open as aread
import os.path
import random
import vlc
import youtube_dl

#***********************************************************************************#
#                                   Main Class/Cog                                  #
#***********************************************************************************#

class Music:

    def __init__(self, bot):
        # Save reference to passed bot instance
        self.bot = bot
        
        # Connect to database and create operation cursor
        self.con = psycopg2.connect(database=DATABASE,user=USER,password=PASSWORD,host=HOST,port=PORT)
        self.cur=self.con.cursor()

        # Set up audio task loop
        self.bot.loop.create_task(self.audio_loop())
        self.channel = None
        self.player = vlc.Instance().media_player_new()
        self.player.event_manager().event_attach(vlc.EventType.MediaPlayerEndReached,self.song_finished)
        self.queue_paths = asyncio.Queue()
        self.queue_titles = []
        self.next = False
        self.paused = False
        self.playing = False

        # Save youtube-dl options
        self.opts={
                'format':'bestaudio',
                'outtmpl':'',
                'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'m4a'}],
                }

    async def audio_loop(self):
        while True:
            self.next = False
            media_path = await self.queue_paths.get()
            if not os.path.isfile(media_path):
                print('Media does not exist... Redownloading')
                print(media_path[6:-4])
                await self.download(media_path[6:-4])
            else:
                self.player.set_media(vlc.Instance().media_new_path(media_path))
                self.player.play()
                self.playing = True

                # Now playing message
                title = self.queue_titles[0][0]
                artist = self.queue_titles[0][1]
                await self.bot.send_message(self.channel,'Now Playing: {0} - {1}'.format(title,artist))
                self.queue_titles = self.queue_titles[1:]
                while not self.next:
                    await asyncio.sleep(1)
                self.player.stop()
                self.playing = False

    def song_finished(self, event):
        if event.type == vlc.EventType.MediaPlayerEndReached:
            self.next = True

#***********************************************************************************#
#                                   Non-Commands                                    #
#***********************************************************************************#

    # Downloads key.m4a from Youtube to Music/
    async def download(self, key):
        try:
            self.opts['outtmpl'] = ('Music/'+key+'.m4a')
            with youtube_dl.YoutubeDL(self.opts) as ydl:
                ydl.download(['https://www.youtube.com/?v='+key])
        except(...):
            await self.bot.send_message(self.channel,'Download error...')
            print(e)

    # Searches album table
    async def search_album(self, content):
        return

    # Searches artist table
    async def search_artist(self, content):
        return
    
    # Searches music table
    async def search_music(self, content):
        cut = content.find(' ')
        param = content[:cut]
        term = content[cut+1:]
        if not (param == 'title' or param == 'artist' or param == 'genre'):
            param = 'title'
            term = content
        if param == 'genre':
            self.cur.execute("select key, genre from genre where {0} like '{1}';".format(param,term))
            results = self.cur.fetchall()
            returns = []
            for result in results:
                term = result[0]
                self.cur.execute("select title, artist, key from music where key like '{0}';".format(term))
                returns += self.cur.fetchall()
            print(returns)
            return returns
        else:
            self.cur.execute("select title, artist, key from music where {0} like '%{1}%';".format(param,term))
            return self.cur.fetchall()

    # Helper function to convert strings to lists (splits at spaces)
    async def string_split(self, s):
        result = []
        cut = s.find(' ')
        while cut != -1:
            result.append(s[:cut])
            s = s[cut+1:]
            cut = s.find(' ')
        result.append(s)
        return result

#***********************************************************************************#
#                               Database Control Commands                           #
#***********************************************************************************#
    
    @commands.command(pass_context=True, no_pm=True)
    async def add(self, ctx):

        request = await self.string_split(ctx.message.content)

        # Check for correct parameters
        if len(request) == 2:
            await self.bot.send_message(ctx.message.channel, 'Try "ia add [song | album | artist | label ]"')
            return

        # Add song
        if request[2] == 'song':
            # Get title
            await self.bot.send_message(ctx.message.channel, 'What is the song called?')
            title_m = await self.bot.wait_for_message(author=ctx.message.author)
            title = (title_m.content).lower()

            # Get artist
            await self.bot.send_message(ctx.message.channel, 'Who is the artist?')
            artist_m = await self.bot.wait_for_message(author=ctx.message.author)
            artist = (artist_m.content).lower()
            print(artist)

            # Get album
            yAlbum = ''
            while yAlbum != 'y' and yAlbum != 'n':
                await self.bot.send_message(ctx.message.channel, 'Is the song from an album? (y/n)')
                yAlbum_m = await self.bot.wait_for_message(author=ctx.message.author)
                yAlbum = (yAlbum_m.content).lower()
                print(yAlbum)
            if yAlbum == 'y':
                await self.bot.send_message(ctx.message.channel, 'What is the name of the album?')
                album_m = await self.bot.wait_for_message(author=ctx.message.author)
                album = (album_m.content).lower()


            # Get genre
            await self.bot.send_message(ctx.message.channel, 'What is song\'s genre(s)?')
            await self.bot.send_message(ctx.message.channel, 'If there is multiple please separate with a comma...')
            genre_m = await self.bot.wait_for_message(author=ctx.message.author)
            genre_s = (genre_m.content).lower()

            # Proccess genres into list
            genres = []
            cut = genre_s.find(',')
            while cut != -1:
                genres.append(genre_s[:cut])
                genre_s = genre_s[cut+2:]
                cut = genre_s.find(',')
            genres.append(genre_s)

            # Get link
            await self.bot.send_message(ctx.message.channel, 'What is the link to the song?')
            link_m = await self.bot.wait_for_message(author=ctx.message.author)

            # Cut link to get unique key
            cut = link_m.content.find('=')+1
            key = link_m.content[cut:]

            # Attempt download
            await self.bot.send_message(ctx.message.channel, 'Downloading...')
            await self.download(key)

            # Get length
            tag = aread('Music/{0}.m4a'.format(key))
            length = int(tag.duration)
            print(length)

            # Attempt database insertion
            await self.bot.send_message(ctx.message.channel, 'Adding "{0}" to database'.format(title))
            try:

                # Insert with album
                if yAlbum == 'y':
                    query = "insert into music(title, artist, album, key, length) values ('{0}', '{1}', '{2}', '{3}', '{4}');"
                    self.cur.execute(query.format(title, artist, album, key, length))

                # Insert without album
                else:
                    query = "insert into music(title, artist, key, length) values ('{0}', '{1}', '{2}', '{3}');"
                    self.cur.execute(query.format(title, artist, key, length))

                # Insert all genres
                for genre in genres:
                    query = "insert into genre(key, genre) values ('{0}', '{1}');"
                    self.cur.execute(query.format(key, genre))

                # Save successful changes
                self.con.commit()
                await self.bot.send_message(ctx.message.channel, 'Database modified successfully!')

            # If insertion fails
            except psycopg2.Error as e:
                await self.bot.send_message(ctx.message.channel,'Insert error...')
                self.con.rollback()
                print(e)

            return
        
        # Add artist
        elif request[2] == 'artist':
            # Get name
            await self.bot.send_message(ctx.message.channel, 'What is the artist\'s name?')
            name_m = await self.bot.wait_for_message(author=ctx.message.author)
            name = (name_m.content).lower()
            
            # Get founded
            await self.bot.send_message(ctx.message.channel, 'What year was the band founded?')
            founded_m = await self.bot.wait_for_message(author=ctx.message.author)
            founded = (founded_m.content).lower()
			
	    # Attempt database insertion
            await self.bot.send_message(ctx.message.channel, 'Adding "{0}" to database'.format(name))
            try:
                query = "insert into artist(name, founded) values ('{0}', '{1}');"
                self.cur.execute(query.format(name, founded))

                # Save successful changes
                self.con.commit()
                await self.bot.send_message(ctx.message.channel, 'Database modified successfully!')

            # If insertion fails
            except psycopg2.Error as e:
                await self.bot.send_message(ctx.message.channel,'Insert error...')
                self.con.rollback()
                print(e)
				
            return

        # Add album
        elif request[2] == 'album':
            return

        # Add label
        elif request[2] == 'label':
            return

        # Invalid parameter
        else:
            await self.bot.send_message(ctx.message.channel, 'Try "ia add [song | album | artist | label ]"')
            return

    @commands.command(pass_context=True, no_pm=True)
    async def edit(self, ctx):
        return

#***********************************************************************************#
#                               Media Control Commands                              #
#***********************************************************************************#

    @commands.command(pass_context=True, no_pm=True)
    async def clear(self, ctx):
        if self.queue_titles == []:
            await self.bot.send_message(ctx.message.channel,"Queue is empty...")
        else:
            self.queue_titles = []
            self.queue_paths = asyncio.Queue()
            await self.bot.send_message(ctx.message.channel,"Queue cleared!")

    # Pauses audio loop
    @commands.command(pass_context=True, no_pm=True)
    async def pause(self, ctx):
        if self.playing:
            if not self.paused:
                self.paused = True
                self.player.pause()
                await self.bot.send_message(ctx.message.channel,"Media playback paused...")
            else:
                self.paused = False
                self.player.pause()
                await self.bot.send_message(ctx.message.channel,"Media playback resumed!")
        else:
            await self.bot.send_message(ctx.message.channel,'Nothing is playing...')


    # Enqueues from database
    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx):
        try:
            self.channel = ctx.message.channel
            results = await self.search_music(ctx.message.content[8:])

            # No results
            if len(results) < 1:
                await self.bot.send_message(ctx.message.channel,'No results...')

            # Exactly one result
            elif len(results) == 1:
                await self.bot.send_message(ctx.message.channel,'Enqueing: '+results[0][0]+" - "+results[0][1])
                self.queue_titles.append([results[0][0].title(),results[0][1].title()])
                await self.queue_paths.put("Music/"+results[0][2]+".m4a")

            # Multiple results
            else:
                await self.bot.send_message(ctx.message.channel,'Multiple results, pick a number or all...')
                all_results = ''
                for i in range(len(results)):
                    all_results += str(i+1)+': '+results[i][0]+' - '+results[i][1]+'\n'
                await self.bot.send_message(ctx.message.channel, all_results)
                choice_m = await self.bot.wait_for_message(author=ctx.message.author)
                choice = choice_m.content

                # Play all results
                if choice == 'all':
                    await self.bot.send_message(ctx.message.channel,'Enqueing: all results')
                    for r in results:
                        await self.queue_paths.put("Music/"+r[2]+".m4a")
                        self.queue_titles.append([r[0].title(),r[1].title()])

                # Play one result
                else:
                    await self.bot.send_message(ctx.message.channel,'Enqueing: '+results[int(choice)-1][0])
                    await self.queue_paths.put("Music/"+results[int(choice)-1][2]+".m4a")
                    self.queue_titles.append(results[int(choice)-1][0].title(),results[int(choice)-1][1].title())

        except psycopg2.Error as e:
            await self.bot.send_message(ctx.message.channel,'Retrieval error...')
            print(e)

    # Prints names of songs in queue
    @commands.command(pass_context=True, no_pm=True)
    async def queue(self, ctx):
        if self.queue_paths.empty(): 
            await self.bot.send_message(ctx.message.channel, 'Queue is empty...')
        else:
            q_str = ''
            for i in range(len(self.queue_titles)):
                q_str += (str(i+1)+': {0} - {1}\n'.format(self.queue_titles[i][0],self.queue_titles[i][1]))
            await self.bot.send_message(ctx.message.channel, 'Current Queue:\n'+q_str)

    
    @commands.command(pass_context=True, no_pm=True)
    async def shuffle(self, ctx):
        if not self.queue_paths.empty():

            # Store values in queue_paths
            temp = []
            for i in range(self.queue_paths.qsize()):
                temp.append(await self.queue_paths.get())

            # Shuffle queue_paths and queue_titles at once
            c = list(zip(temp,self.queue_titles))
            random.shuffle(c)
            temp, self.queue_titles = list(zip(*c))
            for i in range(len(temp)):
                await self.queue_paths.put(temp[i])
            await self.bot.send_message(ctx.message.channel,'Shuffled!')

        else:
            await self.bot.send_message(ctx.message.channel,'Queue is empty...')
    
    # Ends the current song
    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        if self.playing:
            await self.bot.send_message(ctx.message.channel,'Skipping...')
            self.next = True
        else:
            await self.bot.send_message(ctx.message.channel,'Nothing is playing...')

#***********************************************************************************#
#                           Discord Client Initialization                           #
#***********************************************************************************#

client=commands.Bot(command_prefix=commands.when_mentioned_or('ia '))
client.add_cog(Music(client))

@client.event
async def on_ready():
    print('User: '+str(client.user.name))
    print('ID: '+str(client.user.id))
    print('Ready!')

client.run(TOKEN)
