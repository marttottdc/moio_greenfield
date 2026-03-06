
from moio_platform.lib.openai_gpt_api import MoioOpenai

from portal.models import TenantConfiguration
from recruiter.models import Candidate, JobPosting
import umap.umap_ as umap

import numpy as np
import pandas as pd
import plotly.express as px
from datetime import timedelta
from django.utils import timezone
from sklearn.cluster import KMeans

def plot_clusters(tenant, date_range=200):


    # Define the date range
    start_date = timezone.now() - timedelta(days=date_range)
    end_date = timezone.now()

    # Fetch job postings and candidates
    job_postings = JobPosting.objects.filter(tenant=tenant)
    candidates = Candidate.objects.filter(tenant=tenant, created__range=[start_date, end_date])

    # Initialize your OpenAI helper class
    config = TenantConfiguration.objects.get(tenant=tenant)
    mo = MoioOpenai(config.openai_api_key, config.openai_default_model)

    # Generate embeddings
    job_embeddings = [mo.get_embedding(jp.description) for jp in job_postings]
    candidate_embeddings = [candidate.embedding for candidate in candidates]
    all_embeddings = np.array(job_embeddings + candidate_embeddings)

    # Get labels for hover information
    job_descriptions = [jp.description for jp in job_postings]
    candidate_names = [candidate.recruiter_summary for candidate in candidates]

    # Dimensionality reduction to 2D
    reducer = umap.UMAP(n_components=2, random_state=0)
    reduced_embeddings = reducer.fit_transform(all_embeddings)

    # Clustering with k-means
    kmeans = KMeans(n_clusters=5, random_state=0)
    labels = kmeans.fit_predict(reduced_embeddings)

    # Prepare data for plotting without a loop
    num_job_postings = len(job_postings)
    num_candidates = len(candidates)

    # Coordinates
    x_coords = reduced_embeddings[:, 0]
    y_coords = reduced_embeddings[:, 1]

    # Labels
    labels_text = np.array(job_descriptions + candidate_names)

    # Types
    types = np.array(['Job Description'] * num_job_postings + ['Candidate'] * num_candidates)

    # Clusters
    clusters = labels.astype(int)

    # Create DataFrame
    df = pd.DataFrame({
        'x': x_coords,
        'y': y_coords,
        'label': labels_text,
        'type': types,
        'cluster': clusters
    })

    # Create scatter plot
    fig = px.scatter(
        df,
        x='x',
        y='y',
        color='cluster',
        symbol='type',
        hover_data=['label']
    )
    fig.update_layout(clickmode="event+select")
    return fig

