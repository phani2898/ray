import requests
import json
from datetime import datetime, timezone, timedelta
import re
import subprocess
from typing import Set


def list_commit_shas():
    """
    Get list of commit SHAs on ray master branch from at least 30 days ago.
    """
    owner = "ray-project"
    repo = "ray"
    token = "put-your-github-token-here"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-Github-Api_Version": "2022-11-28",
    }
    current_time = datetime.now(timezone.utc)
    time_bound = current_time - timedelta(days=30)
    time_bound = datetime.strftime(time_bound, "%Y-%m-%dT%H:%M:%SZ")
    params = {
        "sha": "master",
        "per_page": 1,
        "page": 1,
        "since": "2023-08-23T00:00:00Z",
        "until": time_bound,
    }

    def get_commit_count():
        response = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            headers=headers,
            params=params,
        )
        pattern = r"&page=(\d+)"
        commit_count = re.findall(pattern, response.headers["Link"])[1]
        return commit_count

    commit_count = get_commit_count()
    params["per_page"] = 100
    page_count = int(commit_count) // params["per_page"] + 1

    commit_shas = set()
    for page in range(page_count, 0, -1):
        params["page"] = page
        response = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            headers=headers,
            params=params,
        )
        commits = response.json()
        for commit in commits:
            commit_time = commit["commit"]["author"]["date"]
            commit_time = datetime.fromisoformat(commit_time)
            time_delta = current_time - commit_time
            if time_delta.days > 30:
                commit_shas.add(commit["sha"][:6])
            else:
                return commit_shas
    return commit_shas


def get_docker_token():
    service = "registry.docker.io"
    scope = "repository:rayproject/ray:pull"
    # The URL for token authentication
    url = f"https://auth.docker.io/token?service={service}&scope={scope}"
    response = requests.get(url)
    token = response.json().get("token")
    return token


def count_docker_tags():
    """
    Count number of tags from rayproject/ray repository.
    """
    response = requests.get(
        "https://hub.docker.com/v2/namespaces/rayproject/repositories/ray/tags"
    )
    tag_count = response.json()["count"]
    return tag_count


def get_image_creation_time(repository: str, tag: str):
    """
    Get the creation time of the image from the tag image config.
    """
    res = subprocess.run(
        ["crane", "config", f"{repository}:{tag}"], capture_output=True, text=True
    )
    if res.returncode != 0 or not res.stdout:
        return None
    manifest = json.loads(res.stdout)
    created = manifest["created"]
    created_time = datetime.fromisoformat(created)
    return created_time


def get_auth_token_docker_hub(username: str, password: str):
    params = {
        "username": username,
        "password": password,
    }
    headers = {
        "Content-Type": "application/json",
    }
    response = requests.post(
        "https://hub.docker.com/v2/users/login", headers=headers, params=params
    )
    token = response.json().get("token")
    return token


def delete_tags(namespace: str, repository: str, tags: list[str]):
    """
    Delete tag from Docker Hub repo.
    """
    token = get_auth_token_docker_hub("username", "password")
    headers = {
        "Authorization": f"Bearer {token}",
    }
    for tag in tags:
        print(f"Deleting {tag}")  # TODO: delete this line
        url = f"https://hub.docker.com/v2/repositories/{namespace}/{repository}/tags/{tag}"
        response = requests.delete(url, headers=headers)
        if response.status_code != 204:
            print(f"Failed to delete {tag}")


def query_tags_to_delete(
    page_count: int, commit_short_shas: Set[str], page_size: int = 100
):
    """
    Query tags to delete from rayproject/ray repository.
    """
    headers = {
        "Authorization": f"Bearer {get_docker_token()}",
    }
    repository = "rayproject/ray"
    current_time = datetime.now(timezone.utc)
    tags_to_delete = []
    for page in range(page_count, 0, -1):
        print("Querying page ", page)  # Replace with log
        response = requests.get(
            "https://hub.docker.com/v2/namespaces/rayproject/repositories/ray/tags",
            params={"page": page, "page_size": 100},
            headers=headers,
        )
        result = response.json()["results"]
        tags = [tag["name"] for tag in result]
        # Check if tag is in list of commit SHAs
        commit_tags = [
            tag
            for tag in tags
            if len(tag.split("-")[0]) == 6 and tag.split("-")[0] in commit_short_shas
        ]

        for tag in commit_tags:
            created_time = get_image_creation_time(repository, tag)
            if created_time is None:
                print(f"Failed to get creation time for {tag}")  # replace with log
                continue
            time_difference = current_time - created_time
            if time_difference.days > 30:
                tags_to_delete.append(tag)
            else:
                return tags_to_delete
    return tags_to_delete


def main():
    page_size = 100
    # Get list of commit SHAs from at least 30 days ago
    commit_shas = list_commit_shas()
    print("Commit count: ", len(commit_shas))  # Replace with log

    docker_tag_count = count_docker_tags()
    print("Docker tag count: ", docker_tag_count)  # Replace with log

    page_count = docker_tag_count // page_size + 1
    tags_to_delete = query_tags_to_delete(page_count, commit_shas, page_size)
    # delete_tags("rayproject", "ray", tags_to_delete)


if __name__ == "__main__":
    main()
