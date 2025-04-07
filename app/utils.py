import matplotlib.pyplot as plt
from io import BytesIO
import base64
from flask_wtf.csrf import CSRFProtect
def create_pie_chart(reviews):
    sentiments = [review.sentiment for review in reviews]
    sentiment_counts = {sentiment: sentiments.count(sentiment) for sentiment in set(sentiments)}
    plt.pie(sentiment_counts.values(), labels=sentiment_counts.keys(), autopct='%1.1f%%')
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.clf()  # Clear the plot
    plt.close()  # Close the figure
    return image_base64


import requests
from flask import current_app

import google.generativeai as genai

def configure_gemini(api_key):
    genai.configure(api_key=api_key)

def generate_ai_reply(review_text):
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"""Generate a professional customer service response to this review:
        Review: "{review_text}"
        Response must be: 
        - 2-3 sentences
        - Empathetic
        - Solution-oriented
        - Brand-neutral
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error generating reply: {str(e)}"