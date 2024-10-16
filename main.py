import streamlit as st
import pandas as pd
import re
import requests
from st_clickable_images import clickable_images
from supabase import create_client, Client
from datetime import datetime
import uuid  # Add this import for generating unique IDs

google_maps_api_key = st.secrets["GOOGLE_MAPS_API_KEY"]

# Set up Supabase client
supabase: Client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def snake_case(s):
    s = re.sub(r'[^a-zA-Z0-9]', ' ', s).lower().replace(' ', '_')
    return s

def convert_price_level(price_level):
    price_map = {
        'PRICE_LEVEL_INEXPENSIVE': '$',
        'PRICE_LEVEL_MODERATE': '$$',
        'PRICE_LEVEL_EXPENSIVE': '$$$',
        'PRICE_LEVEL_VERY_EXPENSIVE': '$$$$'
    }
    return price_map.get(price_level, 'N/A')

st.set_page_config(page_title='Google Maps Gems', page_icon='⭐️', layout='wide')
st.title("Find Gems on Google Maps")
st.info("\"The best places have a 4.9 rating and <100 reviews on Google Maps.\" - [Spencer](https://x.com/spenciefy)\n\n*Note: Searches don't always find every new place, the more specific the better.*")

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    query = st.text_input(
        "Search by type of place and where",
        value="restaurants in greenpoint, brooklyn",
        help="e.g. restaurants in lower east side, new york",
        key="search_query"
    )

with col2:
    min_rating = st.slider(
        "Minimum Rating",
        min_value=4.5,
        max_value=5.0,
        value=4.7,
        step=0.1
    )

with col3:
    max_reviews = st.slider(
        "Maximum Reviews",
        min_value=50,
        max_value=500,
        value=100,
        step=50
    )

# Function to fetch places from Google Places API
def fetch_places(query, min_rating, max_reviews):
    url = 'https://places.googleapis.com/v1/places:searchText'
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': google_maps_api_key,
        'X-Goog-FieldMask': 'nextPageToken,places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.googleMapsUri,places.priceLevel,places.photos,places.reviews,places.location,places.primaryTypeDisplayName,places.primaryType,places.types,places.websiteUri'
    }
    data = {
        "textQuery": query,
        "minRating": 4.5  # Set this to 4.5 to get a wider range, we'll filter further in Python
    }
    
    all_places = []
    next_page_token = None
    
    while True:
        if next_page_token:
            data["pageToken"] = next_page_token
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code != 200:
            print(f"Error response: {response.text}")
            break
        
        result = response.json()
        
        if 'places' in result:
            filtered_places = [
                place for place in result['places']
                if place.get('rating', 0) >= min_rating and place.get('userRatingCount', 0) <= max_reviews
            ]
            all_places.extend(filtered_places)
        
        next_page_token = result.get('nextPageToken')
        if not next_page_token:
            break
    
    return all_places

def create_dataframe(places):
    data = []
    for place in places:
        photo_urls = []
        if 'photos' in place:
            for photo in place['photos']:
                photo_reference = photo['name'].split('/')[-1]
                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={photo_reference}&key={google_maps_api_key}"
                photo_urls.append(photo_url)
        
        reviews = place.get('reviews', [])
        review_details = [{
            'text': review['text']['text'],
            'rating': review.get('rating', 'N/A'),
            'author_name': review.get('authorAttribution', {}).get('displayName', 'Anonymous'),
            'author_photo': review.get('authorAttribution', {}).get('photoUri', ''),
            'publish_time': review.get('relativePublishTimeDescription', 'N/A')
        } for review in reviews if 'text' in review]
        
        location = place.get('location', {})
        latitude = location.get('latitude', 'N/A')
        longitude = location.get('longitude', 'N/A')
        
        primary_type_display = place.get('primaryTypeDisplayName', {}).get('text', 'N/A')
        
        data.append({
            'place_id': place['id'],  # Keep the Google Maps place_id
            'name': place['displayName']['text'],
            'rating': place.get('rating', 'N/A'),
            'user_ratings_total': place.get('userRatingCount', 'N/A'),
            'category': primary_type_display,
            'primary_type': place.get('primaryType', 'N/A'),
            'types': ', '.join(place.get('types', [])),
            'url': place.get('googleMapsUri', 'N/A'),
            'website': place.get('websiteUri', 'N/A'),
            'address': place['formattedAddress'],
            'price_level': convert_price_level(place.get('priceLevel', 'N/A')),
            'photos': photo_urls,
            'reviews': review_details,
            'latitude': latitude,
            'longitude': longitude,
            'search_query': query,
            'last_updated': datetime.now().isoformat()
        })
    return data

def save_to_supabase(places):
    for place in places:
        # Always insert a new entry
        supabase.table('gmaps_gems').insert(place).execute()

# Function to perform the search
def perform_search():
    with st.spinner("Searching for places..."):
        places = fetch_places(query, min_rating, max_reviews)
        data = create_dataframe(places)
        
        # Save results to Supabase
        save_to_supabase(data)
        
        # Convert data to DataFrame for display
        df = pd.DataFrame(data)
        
        # Sort the DataFrame by rating, from highest to lowest
        df = df.sort_values(by=['rating', 'user_ratings_total'], ascending=[False, True])
        
        # Reset the index (but don't add it as a column)
        df = df.reset_index(drop=True)
        
    st.write(f"Found {len(df)} places with rating {min_rating}+ and less than {max_reviews} reviews:")
    
    # Display the DataFrame with selected columns, including place_id
    st.dataframe(df[['name', 'place_id', 'rating', 'user_ratings_total', 'category', 'url', 'website', 'address', 'price_level']])
    
    # Display photos, reviews, and location for each place
    for index, row in df.iterrows():
        st.write(f"### {index + 1}. {row['name']}: {row['rating']}⭐ ({row['user_ratings_total']} reviews)")
        st.write(f"**Category:** {row['category']}")
        st.write(f"**[View on Google Maps]({row['url']})**")
        st.write(f"**Address:** {row['address']}")
        if row['website'] != 'N/A':
            st.write(f"**Website:** [{row['website']}]({row['website']})")
        
        # Display photos using clickable_images
        if row['photos']:
            st.image(row['photos'], width=200)

        if row['reviews']:
            st.write("#### Reviews:")
            # Create a horizontal container for reviews
            review_container = st.container()
            with review_container:
                # Use columns to create a horizontal scroll effect
                review_cols = st.columns(len(row['reviews']))
                for i, review in enumerate(row['reviews']):
                    with review_cols[i]:
                        col1, col2 = st.columns([1, 4])
                        with col1:
                            if review['author_photo']:
                                st.image(review['author_photo'], width=30)
                          
                        with col2:
                            st.markdown(f"**{review['author_name']}**")
                        st.markdown(f"{'⭐' * int(review['rating'])}")
                        st.markdown(f"<small>{review['publish_time']}</small>", unsafe_allow_html=True)
                        st.markdown(f"<div style='height: 150px; overflow-y: auto;'>{review['text']}</div>", unsafe_allow_html=True)

        # Add CSS to enable horizontal scrolling and set max height for reviews
        st.markdown("""
        <style>
        .stHorizontalBlock {
            overflow-x: auto;
            white-space: nowrap;
        }
        .stHorizontalBlock > div {
            display: inline-block;
            vertical-align: top;
            white-space: normal;
            margin-right: 10px;
            width: 250px;  /* Set a fixed width for each review column */
        }
        .stMarkdown {
            max-width: 100%;
        }
        small {
            font-size: 0.8em;
            color: #666;
            display: block;
            margin-top: -5px;  /* Negative margin to reduce space */
        }
        /* Decrease spacing between markdown elements in reviews */
        .stHorizontalBlock > div .stMarkdown {
            margin-bottom: 0.5rem;
        }
        .stHorizontalBlock > div .stMarkdown p {
            margin-bottom: 0.2rem;
        }
        /* Remove space between stars and publish time */
        .stHorizontalBlock > div .stMarkdown p:nth-of-type(2) {
            margin-bottom: 0;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.write("---")

# Check if the user clicked the search button or pressed Enter in the search box
if st.button("Search") or (query != st.session_state.get('previous_query', '') and st.session_state.get('previous_query') is not None):
    st.session_state['previous_query'] = query
    perform_search()

# Initialize the previous_query in session state if it doesn't exist
if 'previous_query' not in st.session_state:
    st.session_state['previous_query'] = None

# Add this CSS to your existing st.markdown call or create a new one
st.markdown("""
<style>
    .fullScreen {
        position: fixed;
        top: 0;
        left: 0;
        bottom: 0;
        right: 0;
        width: 100vw;
        height: 100vh;
        object-fit: contain;
        z-index: 9999;
        background: rgba(0, 0, 0, 0.8);
        display: none;
    }
    .fullScreen img {
        width: 100%;
        height: 100%;
        object-fit: contain;
    }
</style>
""", unsafe_allow_html=True)
