import requests


class HiringRoomAPI:
# https://api.hiringroom.com/#/

    def __init__(self, client_id, client_secret, username, password):
        self.token = None
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password

        url = 'https://api.hiringroom.com/v0/authenticate/login/users'

        # Headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "my-app"
        }
        payload = {
                    "grand_type": "password",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "username": username,
                    "password": password
                }

        response = requests.post(url, headers=headers, json=payload)

        print("Status Code:", response.status_code)
        self.token = response.json()["token"]

    def get_postulants (self, page=0, page_size=100, max_attempts=10):

        url = "https://api.hiringroom.com/v0/postulants/"

        headers = {
            "Accept": "application/json",
            "User-Agent": "my-app"

        }

        params = {
            "page": page,
            "pageSize": page_size,
            "token": self.token
        }
        attempt = 0

        while attempt <= max_attempts:
            print(f"Attempt {attempt}")
            try:
                response = requests.get(url, headers=headers, params=params)
                if response.status_code == 200:

                    return response.json()
                else:
                    print("Failed:", response.status_code, response.text)
            except:
                attempt += 1

    def get_vacantes(self, page=0, page_size=100, max_attempts=10):

        url = "https://api.hiringroom.com/v0/vacancies/"


        headers = {
            "Accept": "application/json",
            "User-Agent": "my-app"

        }

        params = {
            "page": page,
            "pageSize": page_size,
            "token": self.token
        }
        attempt = 0

        while attempt <= max_attempts:
            print(f"Attempt {attempt}")
            try:
                response = requests.get(url, headers=headers, params=params)
                if response.status_code == 200:

                    return response.json()
                else:
                    print("Failed:", response.status_code, response.text)

            except:
                attempt += 1