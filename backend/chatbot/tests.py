from django.db import models
from chatbot.models.chatbot_session import ChatbotMemory  # Adjust import based on your app structure
import pandas as pd

# Fetch all utterances, ordered by timestamp
utterances = ChatbotMemory.objects.all().order_by('created').select_related('session')

# Convert to a list of dictionaries
data = [
    {
        'session_id': utt.session_id,
        'role': utt.role,
        'created': utt.created,
        'content': utt.content
    }
    for utt in utterances
]

# Convert to DataFrame
df = pd.DataFrame(data)


# Function to calculate stats per session and overall
def calculate_response_time_stats(df):
    if df.empty:
        return {}, {'mean': 0, 'median': 0, 'max': 0, 'min': 0}

    session_groups = df.groupby('session_id')
    stats_per_session = {}
    all_response_times = []  # For overall stats

    for session_id, group in session_groups:
        group = group.sort_values('created')  # Ensure chronological order
        last_user_time = None
        response_times = []

        for _, row in group.iterrows():
            if row['role'] == 'user':
                last_user_time = row['created']  # Update to latest user time
            elif row['role'] == 'assistant' and last_user_time is not None:
                elapsed = (row['created'] - last_user_time).total_seconds()
                response_times.append(elapsed)
                all_response_times.append(elapsed)

        if response_times:
            stats_per_session[session_id] = {
                'mean': pd.Series(response_times).mean(),
                'median': pd.Series(response_times).median(),
                'max': pd.Series(response_times).max(),
                'min': pd.Series(response_times).min()
            }
        else:
            stats_per_session[session_id] = {'mean': 0, 'median': 0, 'max': 0, 'min': 0}

    # Overall stats
    overall_stats = (
        {
            'mean': pd.Series(all_response_times).mean(),
            'median': pd.Series(all_response_times).median(),
            'max': pd.Series(all_response_times).max(),
            'min': pd.Series(all_response_times).min()
        } if all_response_times else {'mean': 0, 'median': 0, 'max': 0, 'min': 0}
    )

    return stats_per_session, overall_stats


# Calculate stats
stats_per_session, overall_stats = calculate_response_time_stats(df)

# Print results
print("Response Time Statistics per Session:")
for session_id, stats in stats_per_session.items():
    print(f"Session {session_id}:")
    print(f"  Mean: {stats['mean']:.2f} seconds")
    print(f"  Median: {stats['median']:.2f} seconds")
    print(f"  Max: {stats['max']:.2f} seconds")
    print(f"  Min: {stats['min']:.2f} seconds")

print("\nOverall Response Time Statistics:")
print(f"  Mean: {overall_stats['mean']:.2f} seconds")
print(f"  Median: {overall_stats['median']:.2f} seconds")
print(f"  Max: {overall_stats['max']:.2f} seconds")
print(f"  Min: {overall_stats['min']:.2f} seconds")