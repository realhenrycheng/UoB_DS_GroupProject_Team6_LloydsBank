import pandas as pd
import numpy as np
import os


def compute_media_score(row, sentiment_floor=0.5):
    """
    Updated comprehensive media score logic based on the design document.
    Exposure (theme_score) serves as the base, modulated by sentiment intensity (avg_csi_score).
    """
    theme = row['theme_score']
    sent = row['avg_csi_score']

    # No valid exposure signal
    if pd.isna(theme):
        return np.nan

    # No sentiment data (if this happens, keep only the base exposure score and apply the floor discount)
    if pd.isna(sent):
        return theme * sentiment_floor

    # Sentiment magnitude modulation: The stronger the sentiment, the closer the coefficient is to 1;
    # the weaker (closer to 0), the closer to 0.5.
    modulation = sentiment_floor + (1 - sentiment_floor) * abs(sent)
    return theme * modulation


def get_sentiment_direction(row, threshold=0.1):
    """
    Output sentiment direction separately for downstream tagging and business routing.
    """
    sent = row['avg_csi_score']
    if pd.isna(sent):
        return 'unknown'
    if sent > threshold:
        return 'positive'
    if sent < -threshold:
        return 'negative'
    return 'neutral'


def generate_news_score_table(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"Error: Cannot find the file '{input_file}'.")
        return

    print(f"Reading file: {input_file}...")
    df = pd.read_csv(input_file)

    print("Calculating media score based on the new Exposure * Modulation logic...")

    # To perfectly adapt to the new design, we apply the functions directly to the DataFrame.

    # Calculate the base media score according to the design document
    df['final_news_score'] = df.apply(compute_media_score, axis=1)

    # Extract and output the sentiment direction
    df['sentiment_direction'] = df.apply(get_sentiment_direction, axis=1)

    print(f"Saving the new file to: {output_file}...")

    # Output only the necessary columns to keep downstream processing clean
    columns_to_keep = ['CompanyNumber', 'final_news_score', 'sentiment_direction']

    # If these columns exist in the original file, keep and output them
    existing_cols = [col for col in columns_to_keep if col in df.columns]

    df[existing_cols].to_csv(output_file, index=False)
    print("Processing complete!")

    print("\n📊 Statistical summary for the 'final_news_score' column:")
    print(df['final_news_score'].describe())

    print("\n📊 Distribution of 'sentiment_direction':")
    print(df['sentiment_direction'].value_counts())


if __name__ == "__main__":
    INPUT_FILENAME = 'final_company_features_100k.csv'
    OUTPUT_FILENAME = 'news_score.csv'
    generate_news_score_table(INPUT_FILENAME, OUTPUT_FILENAME)