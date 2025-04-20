import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import sleep
from openai import OpenAI
import os
import csv
import requests
import json
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import random
import re

# Initialize session state for credentials and workflow steps
if 'email' not in st.session_state:
    st.session_state['email'] = ''
if 'password' not in st.session_state:
    st.session_state['password'] = ''
if 'profile_url' not in st.session_state:
    st.session_state['profile_url'] = ''
if 'openai_api_key' not in st.session_state:
    st.session_state['openai_api_key'] = ''
if 'perplexity_api_key' not in st.session_state:
    st.session_state['perplexity_api_key'] = ''
if 'posts_fetched' not in st.session_state:
    st.session_state['posts_fetched'] = False
if 'ideas_selected' not in st.session_state:
    st.session_state['ideas_selected'] = False
if 'next_picked' not in st.session_state:
    st.session_state['next_picked'] = False
if 'research_done' not in st.session_state:
    st.session_state['research_done'] = False
if 'post_written' not in st.session_state:
    st.session_state['post_written'] = False
if 'cookies' not in st.session_state:
    st.session_state['cookies'] = None
if 'posts_fetched_done' not in st.session_state:
    st.session_state['posts_fetched_done'] = False
if 'user_idea' not in st.session_state:
    st.session_state['user_idea'] = ''
if 'custom_idea_selected' not in st.session_state:
    st.session_state['custom_idea_selected'] = False
if 'fetch_posts' not in st.session_state:
    st.session_state['fetch_posts'] = False
if 'selected_idea' not in st.session_state:
    st.session_state['selected_idea'] = ''
if 'idea_edits' not in st.session_state:
    st.session_state['idea_edits'] = {}
if 'linkedin_posts' not in st.session_state:
    st.session_state['linkedin_posts'] = []

# Function to save post to CSV with clear separation
def save_post_to_csv(post):
    csv_file = 'generated_posts.csv'
    existing_posts = []
    if os.path.exists(csv_file):
        with open(csv_file, 'r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader, None)  # Skip header
            existing_posts = [row[0].replace('------', '').strip() for row in reader if row]
    if post not in existing_posts:
        with open(csv_file, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not os.path.exists(csv_file) or os.path.getsize(csv_file) == 0:
                writer.writerow(['Post'])  # Write header if file is new
            writer.writerow([f"------\n{post}\n------"])
        return True
    return False

# Function to save LinkedIn posts to references.csv
def save_linkedin_posts_to_csv(posts):
    csv_file = 'references.csv'
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        new_posts = [p for p in posts if p not in df['Post'].values]
        if new_posts:
            new_df = pd.DataFrame({'Post': new_posts})
            df = pd.concat([df, new_df], ignore_index=True)
    else:
        df = pd.DataFrame({'Post': posts})
    df.to_csv(csv_file, index=False)

# Function to save ideas to ideas.csv
def save_ideas_to_csv(ideas):
    csv_file = 'ideas.csv'
    existing_ideas = []
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        existing_ideas = df['Idea'].tolist()
    new_ideas = [idea for idea in ideas if idea not in existing_ideas]
    if new_ideas:
        new_df = pd.DataFrame({'Idea': new_ideas})
        if os.path.exists(csv_file):
            df = pd.concat([df, new_df], ignore_index=True)
        else:
            df = new_df
        df.to_csv(csv_file, index=False)

# Function to check if an idea is unique and sufficiently different
def is_idea_unique_and_different(idea, existing_posts, existing_ideas):
    idea_lower = idea.lower()
    for post in existing_posts:
        post_content = post.replace('------', '').strip().lower()
        if (idea_lower in post_content or post_content in idea_lower or
            len(set(idea_lower.split()) & set(post_content.split())) / len(idea_lower.split()) > 0.5):
            return False
    for existing_idea in existing_ideas:
        if existing_idea.lower() == idea_lower or \
           len(set(idea_lower.split()) & set(existing_idea.lower().split())) / len(idea_lower.split()) > 0.5:
            return False
    return True

# Function for Perplexity API research using best model with optimized token usage
def get_perplexity_research(api_key, prompt):
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "sonar-reasoning-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,  # Reduced to minimize token waste
        "temperature": 0.7,
        "top_p": 0.9
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", "No research available")
    except requests.exceptions.RequestException as e:
        return f"Error: {str(e)}"

# Streamlit app with UI
st.title("AI LinkedIn Post Generator")

# Debug session state
st.sidebar.write(f"Debug - posts_fetched: {st.session_state['posts_fetched']}, fetch_posts: {st.session_state['fetch_posts']}, posts_fetched_done: {st.session_state['posts_fetched_done']}")

# Sidebar layout
st.sidebar.header("My Links")
st.sidebar.subheader("Content Ideas")
col1, col2, col3, col4, col5 = st.columns(5)

# Ask for credentials and setup
if not st.session_state['email'] or not st.session_state['password'] or not st.session_state['profile_url'] or not st.session_state['openai_api_key'] or not st.session_state['perplexity_api_key']:
    st.sidebar.subheader("Initial Setup")
    st.session_state['email'] = st.sidebar.text_input("Enter your LinkedIn Email", value=st.session_state['email'], key="email_setup")
    st.session_state['password'] = st.sidebar.text_input("Enter your LinkedIn Password", type="password", value=st.session_state['password'], key="password_setup")
    st.session_state['profile_url'] = st.sidebar.text_input("Enter LinkedIn Profile URL", value=st.session_state['profile_url'], key="url_setup")
    st.session_state['openai_api_key'] = st.sidebar.text_input("Enter OpenAI API Key", type="password", value=st.session_state['openai_api_key'], key="api_setup")
    st.session_state['perplexity_api_key'] = st.sidebar.text_input("Enter Perplexity API Key", type="password", value=st.session_state['perplexity_api_key'], key="perplexity_setup")
    st.session_state['fetch_posts'] = st.sidebar.checkbox("Fetch Posts from LinkedIn", value=st.session_state['fetch_posts'], key="fetch_posts_setup")
    if st.sidebar.button("Save and Run"):
        if not st.session_state['email'] or not st.session_state['password'] or not st.session_state['profile_url'] or not st.session_state['openai_api_key'] or not st.session_state['perplexity_api_key']:
            st.sidebar.error("Please fill in all fields.")
        else:
            st.session_state['posts_fetched'] = True
            st.session_state['fetch_posts'] = True
            st.rerun()
else:
    st.session_state['fetch_posts'] = st.sidebar.checkbox("Fetch Posts from LinkedIn", value=st.session_state['fetch_posts'], key="fetch_posts_main")
    if st.sidebar.button("Manually Trigger Fetch"):
        st.session_state['posts_fetched'] = True
        st.session_state['fetch_posts'] = True
        st.rerun()

# Fetch LinkedIn posts if enabled
if st.session_state['posts_fetched'] and st.session_state['fetch_posts']:
    with col1:
        st.subheader("Initial Ideas")
        st.write("⧖ Fetching posts...")
        if not st.session_state.get('posts_fetched_done', False):
            with st.spinner("Fetching posts from LinkedIn..."):
                user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
                ]
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--disable-software-rasterizer")
                chrome_options.add_argument("--disable-gpu-compositing")
                chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                try:
                    st.write(f"Attempting to log in with email: {st.session_state['email']}...")
                    if st.session_state['cookies']:
                        driver.get("https://www.linkedin.com")
                        for cookie in st.session_state['cookies']:
                            driver.add_cookie(cookie)
                        driver.refresh()
                        sleep(5)
                        driver.get(st.session_state['profile_url'])
                        WebDriverWait(driver, 20).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed-shared-update-v2"))
                        )
                    else:
                        driver.get("https://www.linkedin.com/login")
                        sleep(2)
                        driver.find_element(By.ID, "username").send_keys(st.session_state['email'])
                        driver.find_element(By.ID, "password").send_keys(st.session_state['password'])
                        driver.find_element(By.XPATH, "//button[@type='submit']").click()
                        sleep(10)
                        st.session_state['cookies'] = driver.get_cookies()
                        driver.get(st.session_state['profile_url'])

                    sleep(5)
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed-shared-update-v2"))
                    )

                    last_height = driver.execute_script("return document.body.scrollHeight")
                    for _ in range(3):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        sleep(3)
                        new_height = driver.execute_script("return document.body.scrollHeight")
                        if new_height == last_height:
                            break
                        last_height = new_height

                    posts = driver.find_elements(By.CSS_SELECTOR, "div.feed-shared-update-v2")
                    post_texts = []
                    for post in posts:
                        text = post.text.strip()
                        if text and text not in post_texts:
                            post_texts.append(text)
                        if len(post_texts) >= 5:
                            break
                    if post_texts:
                        st.session_state['linkedin_posts'] = post_texts[:5]
                        for i, post in enumerate(post_texts[:5], 1):
                            st.session_state[f'post{i}'] = post
                        st.write("Latest 5 LinkedIn Posts:")
                        for i in range(1, 6):
                            st.write(st.session_state.get(f'post{i}', f"No post {i}"))
                        save_linkedin_posts_to_csv(post_texts)
                        st.session_state['posts_fetched_done'] = True
                        st.write("✓ Fetch complete")
                    else:
                        st.error("No posts found. Check profile URL, credentials, or network.")
                except NoSuchElementException as e:
                    st.error(f"Element not found: {str(e)}")
                except TimeoutException as e:
                    st.error(f"Timeout occurred: {str(e)}")
                except Exception as e:
                    st.error(f"Unexpected error: {str(e)}")
                finally:
                    driver.quit()
                    st.rerun()
        else:
            st.write("Latest 5 LinkedIn Posts (cached):")
            for i in range(1, 6):
                st.write(st.session_state.get(f'post{i}', f"No post {i}"))

if (st.session_state.get('posts_fetched_done', False) or not st.session_state['fetch_posts']) and not st.session_state['custom_idea_selected']:
    with col2:
        st.subheader("Select Ideas")
        st.write("⧖ Optional")
        if st.button("Generate 5 Ideas"):
            st.write("⧖ Pending")
            with st.spinner("Selecting ideas..."):
                client = OpenAI(api_key=st.session_state['openai_api_key'])
                posts = [st.session_state.get(f'post{i}', '') for i in range(1, 6) if st.session_state.get(f'post{i}', '')] if st.session_state['fetch_posts'] else []
                csv_file = 'generated_posts.csv'
                existing_posts = []
                if os.path.exists(csv_file):
                    with open(csv_file, 'r', newline='', encoding='utf-8') as file:
                        reader = csv.reader(file)
                        next(reader, None)  # Skip header
                        existing_posts = [row[0].replace('------', '').strip() for row in reader if row]
                ideas_file = 'ideas.csv'
                existing_ideas = []
                if os.path.exists(ideas_file):
                    df = pd.read_csv(ideas_file)
                    existing_ideas = df['Idea'].tolist()
                existing_content = posts + existing_posts + existing_ideas
                prompt = f"Provide 5 concise, unique title ideas based on these LinkedIn posts: {posts}. Ensure each idea is different from the others and from the provided posts, focusing on AI news, blockchain, finance, crypto, AI developments, AI researches, or AI technical papers as of April 20, 2025. Avoid repetition of phrases or concepts."
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}]
                )
                ideas = [line.strip() for line in response.choices[0].message.content.strip().split('\n') if line.strip()]
                unique_ideas = []
                for idea in ideas[:5]:
                    if is_idea_unique_and_different(idea, existing_content, existing_ideas):
                        unique_ideas.append(idea)
                    else:
                        prompt = f"Provide a new concise, unique title idea different from: {', '.join(existing_content + existing_ideas)}. Focus on AI news, blockchain, finance, crypto, AI developments, AI researches, or AI technical papers as of April 20, 2025. Avoid repetition."
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        new_idea = response.choices[0].message.content.strip()
                        if is_idea_unique_and_different(new_idea, existing_content, existing_ideas):
                            unique_ideas.append(new_idea)
                for i, idea in enumerate(unique_ideas[:5], 1):
                    st.session_state[f'idea{i}'] = idea
                    st.session_state['idea_edits'][f'idea{i}'] = idea
                    st.write(f"Idea {i}: {idea}")
                if len(unique_ideas) >= 5:
                    save_ideas_to_csv(unique_ideas)
                    st.session_state['ideas_selected'] = True
                    st.write("✓ Done")
                else:
                    st.error("Unable to generate 5 unique and different title ideas.")
        if st.button("Regenerate Ideas"):
            for i in range(1, 6):
                if f'idea{i}' in st.session_state:
                    del st.session_state[f'idea{i}']
            st.session_state['ideas_selected'] = False
            st.rerun()
        else:
            st.session_state['user_idea'] = st.text_input("Enter your own idea (optional):")
            if st.button("Use My Idea"):
                if st.session_state['user_idea']:
                    st.session_state['next_idea'] = st.session_state['user_idea']
                    st.session_state['custom_idea_selected'] = True
                    st.write(f"Selected idea: {st.session_state['next_idea']}")
                else:
                    st.error("Please enter an idea.")

if (st.session_state['ideas_selected'] or st.session_state['custom_idea_selected']) and not st.session_state['next_picked']:
    with col3:
        st.subheader("Pick Next")
        st.write("⧖ Pending")
        if st.session_state['ideas_selected']:
            ideas = [st.session_state.get(f'idea{i}', '') for i in range(1, 6) if st.session_state.get(f'idea{i}', '')]
            if ideas:
                options = ['Random'] + [f"Idea {i}: {st.session_state.get(f'idea{i}', '')}" for i in range(1, 6) if st.session_state.get(f'idea{i}', '')]
                selected_option = st.selectbox("Choose an idea or select 'Random' for the trending one:", options, index=0)
                if st.button("Confirm Selection"):
                    if selected_option == 'Random':
                        client = OpenAI(api_key=st.session_state['openai_api_key'])
                        prompt = f"From these titles, pick the most trending one as of April 20, 2025, based on the latest trends in AI news, blockchain, finance, crypto, AI developments, AI researches, or AI technical papers. Simplify the topic: {ideas}"
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        next_idea = response.choices[0].message.content.strip()
                    else:
                        next_idea = selected_option.split(': ')[1] if ': ' in selected_option else selected_option
                    st.session_state['selected_idea'] = next_idea
                    st.session_state['next_idea'] = next_idea
                    st.write(f"Selected idea: {next_idea}")
                    st.session_state['next_picked'] = True
                    st.write("✓ Done")
                for i in range(1, 6):
                    if st.session_state.get(f'idea{i}', ''):
                        edited_idea = st.text_input(f"Edit Idea {i}:", value=st.session_state['idea_edits'].get(f'idea{i}', st.session_state[f'idea{i}']), key=f"edit_idea_{i}")
                        if st.button(f"Save Edit for Idea {i}", key=f"save_edit_{i}"):
                            st.session_state[f'idea{i}'] = edited_idea
                            st.session_state['idea_edits'][f'idea{i}'] = edited_idea
                            st.rerun()
        elif st.session_state['custom_idea_selected']:
            client = OpenAI(api_key=st.session_state['openai_api_key'])
            prompt = f"From this title, identify the most trending part as of April 20, 2025, based on the latest trends in AI news, blockchain, finance, crypto, AI developments, AI researches, or AI technical papers. Simplify the topic: {st.session_state['next_idea']}"
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            next_idea = response.choices[0].message.content.strip()
            st.session_state['next_idea'] = next_idea
            st.write(f"Refined trending idea: {next_idea}")
            st.session_state['next_picked'] = True
            st.write("✓ Done")

if st.session_state['next_picked'] and not st.session_state['research_done']:
    with col4:
        st.subheader("Research")
        st.write("⧖ Pending")
        if st.button("Proceed with Research?"):
            with st.spinner("Researching..."):
                perplexity_api_key = st.session_state['perplexity_api_key']
                next_idea = st.session_state.get('next_idea', '')
                if next_idea and perplexity_api_key:
                    prompt = f"Conduct point-to-point research on '{next_idea}' using the latest web data as of April 20, 2025. Focus only on key developments, trends, and insights related to AI news, blockchain, finance, crypto, AI developments, AI researches, or AI technical papers. Return concise bullet points (max 5) without repeating the query or adding fluff. Suggest a short, SEO-optimized title."
                    research = get_perplexity_research(perplexity_api_key, prompt)
                    lines = research.split('\n')
                    seo_title = next((line for line in lines if line.startswith('SEO Title:')), 'No title suggested')
                    if seo_title.startswith('SEO Title:'):
                        st.write(seo_title)
                        research = '\n'.join(line for line in lines if not line.startswith('SEO Title:'))
                    st.session_state['research'] = research
                    st.write(research)
                    st.session_state['research_done'] = True
                    st.write("✓ Done")
                else:
                    st.error("Perplexity API key or idea is missing.")
        if st.button("Regenerate Research"):
            st.session_state['research_done'] = False
            st.rerun()

if st.session_state['research_done'] and not st.session_state['post_written']:
    with col5:
        st.subheader("Write")
        st.write("⧖ Pending")
        if st.button("Generate Post?"):
            with st.spinner("Writing post..."):
                client = OpenAI(api_key=st.session_state['openai_api_key'])
                research = st.session_state.get('research', '')
                ref_csv = 'references.csv'
                old_posts = []
                if os.path.exists(ref_csv):
                    df = pd.read_csv(ref_csv)
                    old_posts = df['Post'].tolist()
                key_points = []
                for post in old_posts:
                    points = re.split(r'\n|-|\*', post)
                    key_points.extend([p.strip() for p in points if p.strip()])
                if research and key_points:
                    prompt = f"Write a concise, casual LinkedIn post under 150 words based on this research: {research} make sure all the important information must be covered and these key points from old posts: {key_points}. Use simple, layman-friendly so that even a non technical guy can understand English with a human touch. Provide a short, catchy, SEO-optimized title (under 10 words) and the post in atmost 3-5 bullet points with main insights. Optimize with keywords from AI news, blockchain, finance, crypto, AI developments, AI researches. Include 3-5 trendy hashtags (e.g., #AI, #Blockchain, #TechTrends2025). Ensure it’s unique and user-friendly."
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    post_content = response.choices[0].message.content.strip()
                    lines = post_content.split('\n')
                    seo_title = next((line for line in lines if line.startswith('SEO Title:')), 'SEO Title: Untitled')
                    post = '\n'.join(line for line in lines if not line.startswith('SEO Title:'))
                    if save_post_to_csv(post):
                        st.write(seo_title)
                        st.write("------")
                        st.write(post)
                        st.session_state['post_written'] = True
                        st.write("✓ Done")
                    else:
                        st.write("Post is a duplicate, generating a new one...")
                        prompt = f"Write a concise, casual LinkedIn post under 150 words based on this research: {research} make sure all the important information must be covered and these key points from old posts: {key_points}. Use simple, layman-friendly so that even a non technical guy can understand English with a human touch. Provide a short, catchy, SEO-optimized title (under 10 words) and the post in atmost 3-5 bullet points with main insights. Optimize with keywords from AI news, blockchain, finance, crypto, AI developments, AI researches. Include 3-5 trendy hashtags (e.g., #AI, #Blockchain, #TechTrends2025). Ensure it’s unique and user-friendly."
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        new_post_content = response.choices[0].message.content.strip()
                        new_lines = new_post_content.split('\n')
                        new_seo_title = next((line for line in new_lines if line.startswith('SEO Title:')), 'SEO Title: Untitled')
                        new_post = '\n'.join(line for line in new_lines if not line.startswith('SEO Title:'))
                        if save_post_to_csv(new_post):
                            st.write(new_seo_title)
                            st.write("------")
                            st.write(new_post)
                            st.session_state['post_written'] = True
                            st.write("✓ Done")
                        else:
                            st.error("Unable to generate a unique post")
        if st.button("Regenerate Post"):
            st.session_state['post_written'] = False
            st.rerun()

st.subheader("Draft")
st.write("⧖ Pending")
st.write("Output")

# Initialize session state for posts and ideas
for i in range(1, 6):
    if f'post{i}' not in st.session_state:
        st.session_state[f'post{i}'] = ''
    if f'idea{i}' not in st.session_state:
        st.session_state[f'idea{i}'] = ''
if 'next_idea' not in st.session_state:
    st.session_state['next_idea'] = ''
if 'research' not in st.session_state:
    st.session_state['research'] = ''
if 'posts_fetched_done' not in st.session_state:
    st.session_state['posts_fetched_done'] = False

# Required libraries
# pip install streamlit selenium webdriver-manager openai pandas requests