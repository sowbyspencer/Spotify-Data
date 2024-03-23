# from flask import Flask, redirect, render_template, request, session, url_for
# from dotenv import load_dotenv
# import os

from flask import Flask, redirect, url_for, render_template, request, session
from urllib.parse import urlencode
from flask import jsonify
from dotenv import load_dotenv
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import render_template, redirect, url_for, session
import os
import requests
import json

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:5000/callback"
SCOPE = "user-library-read"

KEY_MAP = {
    0: 'C',
    1: 'C♯/D♭',
    2: 'D',
    3: 'D♯/E♭',
    4: 'E',
    5: 'F',
    6: 'F♯/G♭',
    7: 'G',
    8: 'G♯/A♭',
    9: 'A',
    10: 'A♯/B♭',
    11: 'B'
}

MODE_MAP = {0: 'Minor', 1: 'Major'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    }
    auth_url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"
    
    print(f"Authorization URL: {auth_url}")  # Debugging print statement
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }
    response = requests.post(token_url, data=payload)
    token_info = response.json()
    session['access_token'] = token_info['access_token']  # Store the token in the session
    return redirect(url_for('liked_songs'))  # Redirect to the 'liked_songs' route

@app.route('/liked_songs')
def liked_songs():
    access_token = session.get('access_token')
    if not access_token:
        return redirect(url_for('login'))
    
    return render_template('liked_songs.html')

# def get_liked_songs(access_token):
#     # Fetch liked songs
#     url = "https://api.spotify.com/v1/me/tracks?limit=50"  # Limit to 50 songs for demonstration
#     headers = {"Authorization": f"Bearer {access_token}"}
#     response = requests.get(url, headers=headers)
#     liked_songs = response.json()
#     return liked_songs

def get_liked_songs(access_token):
    # Initialize an empty list to store all liked songs
    all_liked_songs = []

    # Set the initial URL for fetching liked songs
    url = "https://api.spotify.com/v1/me/tracks?limit=50"

    while url:
        # Make the API request
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(url, headers=headers)
        liked_songs = response.json()

        # Add the fetched songs to the list
        all_liked_songs.extend(liked_songs['items'])

        # Get the URL for the next page of results, if any
        url = liked_songs.get('next')

    return all_liked_songs

def save_liked_songs_to_json(access_token):
    all_liked_songs = get_liked_songs(access_token)  # Assuming this fetches all liked songs

    # Fetch audio features for all tracks in batches
    batch_size = 100
    all_audio_features = []
    for i in range(0, len(all_liked_songs), batch_size):
        print(f"Batch {i}")
        batch_ids = [song['track']['id'] for song in all_liked_songs[i:i + batch_size]]
        audio_features_url = f"https://api.spotify.com/v1/audio-features?ids={','.join(batch_ids)}"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(audio_features_url, headers=headers)
        if response.status_code == 200:
            batch_features = response.json()['audio_features']
            all_audio_features.extend(batch_features)
        else:
            print(f"Error fetching audio features: {response.status_code}")

    # Combine liked songs with their audio features and remove "available_markets"
    for song, features in zip(all_liked_songs, all_audio_features):
        song['track']['audio_features'] = features
        if 'available_markets' in song['track']:
            del song['track']['available_markets']
        if 'available_markets' in song['track']['album']:
            del song['track']['album']['available_markets']

    # Save the data to a JSON file
    with open('liked_songs_with_features.json', 'w') as file:
        json.dump(all_liked_songs, file, indent=4)


def load_liked_songs_from_json():
    with open('liked_songs_with_features.json', 'r') as file:
        liked_songs = json.load(file)
    return liked_songs

@app.route('/api/liked-songs-data')
def liked_songs_data():
    access_token = session.get('access_token')
    if not access_token:
        return jsonify({'error': 'Access token is missing'})

    # Save liked songs with audio features to JSON file
    save_liked_songs_to_json(access_token)

    # Load liked songs from JSON file
    liked_songs = load_liked_songs_from_json()

    # Retrieve DataTables' request parameters
    draw = int(request.args.get('draw', 1))
    start = int(request.args.get('start', 0))
    length = int(request.args.get('length', 10))

    # Paginate the liked songs for the current page
    paginated_songs = liked_songs[start:start + length]

    # Format the data for DataTables
    processed_data = []
    for song in paginated_songs:
        track = song['track']
        audio_features = track.get('audio_features', {})
        key_value = audio_features.get('key')
        actual_key = KEY_MAP.get(key_value, "Unknown")
        mode_value = audio_features.get('mode')
        actual_mode = MODE_MAP.get(mode_value)

        # Construct the dropdown menu for artists
        artist_dropdown = '<div class="dropdown"><button class="dropbtn">{}</button><div class="dropdown-content">'.format(track["artists"][0]["name"])
        for artist in track["artists"]:
            artist_dropdown += '<a href="{}" target="_blank">{}</a>'.format(artist["external_urls"]["spotify"], artist["name"])
        artist_dropdown += '</div></div>'

        # Add the formatted song data to the processed_data list
        processed_data.append([
            f'<a href="{track["album"]["external_urls"]["spotify"]}" target="_blank"><img src="{track["album"]["images"][2]["url"]}" alt="Album Cover" class="album-art"></a>',
            f'<a href="{track["external_urls"]["spotify"]}" target="_blank">{track["name"]}</a>',
            artist_dropdown,
            track["album"]["release_date"],
            track["popularity"],
            f'{track["duration_ms"] // 60000}:{track["duration_ms"] % 60000 // 1000:02}',
            audio_features.get("danceability"),
            audio_features.get("energy"),
            actual_key,
            audio_features.get("loudness"),
            actual_mode,
            audio_features.get("speechiness"),
            audio_features.get("acousticness"),
            audio_features.get("instrumentalness"),
            audio_features.get("liveness"),
            audio_features.get("valence"),
            audio_features.get("tempo"),
            audio_features.get("time_signature")
        ])

    # For server-side processing, determine the total number of records
    total_records = len(liked_songs)
    filtered_records = total_records  # Adjust this if you apply any filtering

    # Generate the response
    response = {
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": filtered_records,
        "data": processed_data
    }
    return jsonify(response)

@app.route('/start-analysis')
def start_analysis():
    # Perform analysis
    analysis()
    return jsonify({'message': 'Analysis complete!'})

@app.route('/analysis')
def analysis():
    try:
        access_token = session.get('access_token')
        if not access_token:
            return redirect(url_for('login'))
        
        all_liked_songs = load_liked_songs_from_json()

        # Convert liked songs data into a Pandas DataFrame
        songs_df = pd.DataFrame([song['track'] for song in all_liked_songs])

        # Extract audio features into separate columns
        for feature in ['danceability', 'energy', 'key', 'mode', 'loudness', 'speechiness', 'acousticness', 'instrumentalness', 'liveness', 'valence', 'tempo', 'time_signature']:
            songs_df[feature] = songs_df['audio_features'].apply(lambda x: x[feature])

        # Create histograms for each feature
        feature_plots = {}
        for feature in ['popularity', 'duration_ms', 'danceability', 'energy', 'key', 'mode', 'loudness', 'speechiness', 'acousticness', 'instrumentalness', 'liveness', 'valence', 'tempo', 'time_signature']:
            plt.figure(figsize=(10, 6))
            songs_df[feature].plot(kind='hist', bins=20)
            plt.title(f'Distribution of {feature.capitalize()}')
            plt.xlabel(feature.capitalize())
            plt.ylabel('Frequency')
            plt.tight_layout()
            plot_path = f'static/{feature}_distribution.png'
            plt.savefig(plot_path)
            plt.close()
            feature_plots[feature] = plot_path

        # Pass the analysis results and the chart paths to the template
        return render_template('analysis.html', feature_plots=feature_plots)
    
    except Exception as e:
        app.logger.error(f"Analysis error: {e}")
        return jsonify({'error': str(e)}), 500





if __name__ == '__main__':
    app.run(debug=True)
