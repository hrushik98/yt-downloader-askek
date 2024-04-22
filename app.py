import os
import certifi
import boto3
from botocore.exceptions import ClientError
import streamlit as st

ACCESS_KEY_ID = st.secrets['ACCESS_KEY_ID']
SECRET_ACCESS_KEY = st.secrets['SECRET_ACCESS_KEY']
BUCKET_NAME = st.secrets['BUCKET_NAME']
s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY_ID, aws_secret_access_key=SECRET_ACCESS_KEY)
os.environ['SSL_CERT_FILE'] = certifi.where()

import streamlit as st
from pytube import YouTube, Channel, Playlist
import os
import json
import uuid

st.set_page_config(page_title="YouTube Video Downloader")
download_option = st.radio("Select download option", ['YouTube URL', 'Playlist', 'Channel'])

def upload_to_s3(file_name, folder_path):
    try:
        s3.upload_file(file_name, BUCKET_NAME, folder_path + '/' + os.path.basename(file_name))
    except ClientError as e:
        print(e)

def download_video(url, channel_name):
    yt = YouTube(url)
    stream = yt.streams.get_highest_resolution()
    video_file_name = stream.download()

    try:
        with open("video_annotations.xml", "w", encoding="utf-8") as annotations_file:
            caption = yt.captions.get_by_language_code('en')
            annotations_file.write(str(caption.xml_captions))

        import xml.etree.ElementTree as ET

        def convert_xml_to_srt(xml_file):
            tree = ET.parse(xml_file)
            root = tree.getroot()
            srt_content = ""
            index = 1
            for p in root.findall('./body/p'):
                start_time = int(p.get('t')) / 1000
                duration = int(p.get('d')) / 1000
                end_time = start_time + duration
                text = p.text.strip().replace('\\\\n', ' ').replace('\\\\r', '')
                srt_content += f"{index}\n"
                srt_content += f"{convert_time_format(start_time)} --> {convert_time_format(end_time)}\n"
                srt_content += f"{text}\n\n"
                index += 1
            return srt_content

        def convert_time_format(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            seconds = int(seconds % 60)
            milliseconds = int((seconds - int(seconds)) * 1000)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

        xml_file = "video_annotations.xml"
        srt_content = convert_xml_to_srt(xml_file)
        with open("video_subtitles.srt", "w") as f:
            f.write(srt_content)

    except Exception as e:
        print(f"Error: {e}")
        if os.path.exists("video_annotations.xml"):
            os.remove("video_annotations.xml")

    thumbnail_file_name = yt.thumbnail_url.split("/")[-1]
    yt.streams.get_by_itag(22).download(filename=thumbnail_file_name)

    video_duration = yt.length

    video_metadata = {
        "id": str(uuid.uuid4()),
        "Title": yt.title,
        "Description": yt.description,
        "Type": "Video",
        "required": None,
        "locale": "en",
        "MediaURL": None,  # Will be updated after uploading to S3
        "thumbnails": [{"url": None}],  # Will be updated after uploading to S3
        "duration": video_duration,
        "Author": yt.author,
        "AuthorUrl": yt.watch_url,
        "License": "CC-Commons",
    }

    video_folder_name = yt.title.replace("/", "_")
    folder_path = f"{channel_name}/{video_folder_name}"

    upload_to_s3(video_file_name, folder_path)
    upload_to_s3("video_annotations.xml", folder_path)
    upload_to_s3("video_subtitles.srt", folder_path)
    upload_to_s3(thumbnail_file_name, folder_path)

    video_metadata["MediaURL"] = f"https://{BUCKET_NAME}.s3.amazonaws.com/{folder_path}/{os.path.basename(video_file_name)}"
    video_metadata["thumbnails"][0]["url"] = f"https://{BUCKET_NAME}.s3.amazonaws.com/{folder_path}/{thumbnail_file_name}"

    with open("metadata.json", "w", encoding="utf-8") as metadata_file:
        json.dump(video_metadata, metadata_file, indent=4)

    upload_to_s3("metadata.json", folder_path)

    os.remove(video_file_name)
    os.remove("video_annotations.xml")
    os.remove("video_subtitles.srt")
    os.remove(thumbnail_file_name)
    os.remove("metadata.json")

    return video_metadata

def download_playlist(playlist_url, channel_name):
    pl = Playlist(playlist_url)
    playlist_id = pl.playlist_id
    playlist_title = pl.title
    playlist_uploader = pl.owner
    playlist_uploader_url = pl.owner_url

    metadata = {
        "Playlist": {
            "id": playlist_id,
            "title": playlist_title,
            "description": "",
            "uploader": playlist_uploader,
            "uploader_url": playlist_uploader_url,
            "extractor_key": "YoutubeTab",
            "Videos": [],
        }
    }

    playlist_folder_name = playlist_title.replace("/", "_")
    folder_path = f"{channel_name}/{playlist_folder_name}"
    os.makedirs(folder_path, exist_ok=True)

    for video in pl.videos:
        video_metadata = download_video(video.watch_url, f"{folder_path}/{video.title.replace('/', '_')}")
        metadata["Playlist"]["Videos"].append(video_metadata)

    with open("metadata.json", "w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, indent=4)

    upload_to_s3("metadata.json", folder_path)
    os.remove("metadata.json")

if download_option == 'YouTube URL':
    url = st.text_input("Enter the YouTube video URL")
    channel_name = st.text_input("Enter the channel name")
    if st.button("Download"):
        st.success("Downloading...")
        download_video(url, channel_name)
        
        st.success("Downloaded")

elif download_option == 'Playlist':
    playlist_url = st.text_input("Enter the YouTube playlist URL")
    channel_name = st.text_input("Enter the channel name")
    if st.button("Download Playlist"):
        st.success("Downloading...")
        download_playlist(playlist_url, channel_name)
        
        st.write("Playlist downloaded")

elif download_option == 'Channel':
    channel_url = st.text_input("Enter the YouTube channel URL")

    def download_channel(channel_url, channel_name):
        c = Channel(channel_url)
        for url in c.video_urls:
            download_video(url, channel_name)

    channel_name = st.text_input("Enter the channel name")
    if st.button("Download Channel"):
        download_channel(channel_url, channel_name)
        st.write("Channel downloaded")
