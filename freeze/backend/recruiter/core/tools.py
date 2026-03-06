from datetime import datetime

import numpy as np
import pandas as pd

from django.db import models
from moio_platform.lib.openai_gpt_api import get_embedding, get_simple_response, image_reader_base64, get_advanced_response

from crm.models import Branch, Contact, Tag

from moio_platform.lib.google_maps_api import haversine, calculate_public_transport_eta

from portal.models import TenantConfiguration
from recruiter.models import CandidateDistances, Candidate


def datetime_handler(x):
    if x is None:
        return ""
    else:
        return x.strftime('%Y-%m-%d %H:%M:%S')


def candidate_distance_to_branches_evaluation_v2(candidate, tenant_configuration, max_duration=45):
    from sklearn.cluster import KMeans

    # Initialize dictionary to store distances
    distances = {}
    branches = Branch.objects.filter(tenant=tenant_configuration.tenant, geocoded=True)

    # Calculate distances to each branch and store in dictionary
    if len(branches) <= 0:
        return distances

    for branch in branches:
        distance = round(haversine(lat1=candidate.latitude,
                                   lon1=candidate.longitude,
                                   lat2=branch.latitude,
                                   lon2=branch.longitude), 2)
        distances[branch] = distance

    # Convert distances dictionary to DataFrame
    df_distances = pd.DataFrame(list(distances.items()), columns=['Branch', 'Distance'])

    # Perform K-means clustering
    n_clusters = 4
    X = np.array(df_distances['Distance']).reshape(-1, 1)
    kmeans = KMeans(n_clusters=n_clusters, random_state=0).fit(X)

    # Get the cluster centers and define thresholds for each cluster
    cluster_centers = kmeans.cluster_centers_
    thresholds = sorted([min(cluster_centers[i]) for i in range(n_clusters)])

    # print("thresholds", thresholds[0], thresholds[1], thresholds[2], thresholds[3])

    # Categorize distances into clusters
    categories = []
    for distance in df_distances['Distance']:
        if distance <= thresholds[0]:
            categories.append("A")
        elif distance <= thresholds[1]:
            categories.append("B")
        elif distance <= thresholds[2]:
            categories.append("C")
        else:
            categories.append("D")

    # Add category column to DataFrame
    df_distances['Category'] = categories

    # Sort the DataFrame by distance
    df_distances = df_distances.sort_values(by='Distance')

    # Iterate over the elements in cluster 0
    reco_branch = {}
    all_distances = []
    min_duration = 100001

    for index, row in df_distances.iterrows():
        # Access individual elements if needed
        branch = row['Branch']
        distance = row['Distance']
        category = row['Category']

        print(f"Candidate: {candidate.pk}, Branch:{branch}, Distance:{distance}, Category: {category} ")

        # Create the CandidateDistances record or update existing ones
        try:
            candidate_distance = CandidateDistances.objects.get(tenant=tenant_configuration.tenant, branch=branch.pk, candidate=candidate)
            candidate_distance.distance = distance
            candidate_distance.distance_category = category

        except CandidateDistances.DoesNotExist:
            candidate_distance = CandidateDistances(
                tenant=tenant_configuration.tenant,
                branch_id=branch.pk,
                candidate=candidate,
                distance=distance,
                distance_category=category
            )

        except CandidateDistances.MultipleObjectsReturned:
            candidate_distance = CandidateDistances.objects.filter(tenant=tenant_configuration.tenant, branch=branch.pk, candidate=candidate).order_by('-pk').first()
            CandidateDistances.objects.filter(tenant=tenant_configuration.tenant, branch=branch.pk, candidate=candidate).exclude(pk=candidate_distance.pk).delete()
            candidate_distance.distance = distance
            candidate_distance.distance_category = category

        #  Create a distance item to add to all_distances list this object may include duration for A Category records
        distance_item = {
            'branch': branch.name,
            'category': category,
            'distance': distance
        }

        if category == "A":

            origin = f"{candidate.latitude},{candidate.longitude}"
            destination = f"{branch.latitude},{branch.longitude}"
            try:
                calculated_duration = calculate_public_transport_eta(origin=origin, destination=destination, google_maps_api_key=tenant_configuration.google_api_key)
            except Exception as e:
                calculated_duration = 100000

            if calculated_duration < min_duration:

                min_duration = calculated_duration
                reco_branch = {
                    "branch": branch.name,
                    "duration": calculated_duration
                }
                print(reco_branch)

            distance_item["duration"] = calculated_duration  # add duration to distance item
            candidate_distance.duration = calculated_duration

        all_distances.append(distance_item)  # add distance item to the list of all distances
        candidate_distance.save()

    return {"reco": reco_branch, "distances": all_distances}


def distance_evaluation_model_training():
    from sklearn.cluster import KMeans
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import train_test_split

    candidates = Candidate.objects.filter(tenant_id=3, latitude__isnull=False, )
    branches = Branch.objects.filter(tenant_id=3, geocoded=True)
    # Initialize list to store distances
    distances_list = []

    # Calculate distances between each candidate and each branch
    for candidate in candidates:
        distances = []
        for branch in branches:
            distance = round(haversine(lat1=candidate.latitude, lon1=candidate.longitude, lat2=branch.latitude,
                                       lon2=branch.longitude), 2)
            distances.append(distance)
        distances_list.append(distances)

    # Convert the list of distances into a numpy array (distance matrix)
    distances_matrix = np.array(distances_list)

    # Define the number of clusters (2: near, far)
    n_clusters = 3

    # Apply K-means clustering to the distances matrix
    kmeans = KMeans(n_clusters=n_clusters, random_state=0)
    cluster_assignments = kmeans.fit_predict(distances_matrix)

    # Split the data into training and testing sets
    X_train, X_test, y_train, y_test = train_test_split(distances_matrix, cluster_assignments, test_size=0.2, random_state=42)

    # Train a logistic regression model
    log_reg_model = LogisticRegression()
    log_reg_model.fit(X_train, y_train)

    # Save the trained model to a file

    #serialized_object = joblib.dump(log_reg_model)

    # Specify the file name and path where you want to save the object
    #file_name = 'logistic_regression_model.pkl'
    #file_path = f'media/models/{file_name}'  # Adjust the path as needed

    # Save the serialized object to the default storage
    #default_storage.save(file_path, ContentFile(serialized_object))



    # Make predictions on the testing set
    y_pred = log_reg_model.predict(X_test)

    print(y_test)
    print(y_pred)

    # Evaluate the model
    accuracy = accuracy_score(y_test, y_pred)
    print("Accuracy:", accuracy)

    return log_reg_model


# Calculate cosine similarity
def calculate_cosine_similarity(candidate_embedding, job_embedding):
    return np.dot(job_embedding, candidate_embedding) / (np.linalg.norm(job_embedding) * np.linalg.norm(candidate_embedding))


def reset_candidate_summaries_and_embeddings(tenant_id):

    for candidate in Candidate.objects.filter(tenant_id=tenant_id):
        candidate.recruiter_summary = ""
        candidate.embedding = None
        print(f'Forgetting summary of {candidate.contact.fullname}')
        candidate.save()


def date_converter(input_date):
    parsed_date = datetime.strptime(input_date, "%d/%m/%Y")
    output_date = parsed_date.strftime("%Y-%m-%d")
    return output_date


def insert_tags(instance: models.Model, tag_list: list, tenant):

    if hasattr(instance, "tags"):
        for tag in tag_list:

            tag = tag.lower()
            try:
                t = Tag.objects.get(name=tag, tenant=tenant)

            except Tag.DoesNotExist:
                t = Tag.objects.create(name=tag, tenant=tenant)
                t.save()

            instance.tags.add(t)
            instance.save()
    else:
        print(f"Field 'tags' does not exist in {instance.__class__.__name__}")
