import requests


def compare_versions(version1, version2):
   return version1 == version2
   # for solve the test version issue, like "v1.1.03i", the normalize will fail
   # def normalize(version):
   #    return tuple(map(int, version.lstrip('v').split('.')))

   # return normalize(version1) == normalize(version2)


def get_latest_version():
   """
   Fetches the latest release version of NMMiner from GitHub API.

   Returns:
       str: Latest version tag (e.g., 'v1.2.3').

   Raises:
       Exception: If the request fails.
   """
   url = 'https://api.github.com/repos/NMminer1024/NMMiner/releases/latest'
   headers = {"Accept": "application/vnd.github.v3+json"}  # Ensure we get the correct API response

   response = requests.get(url, headers=headers, timeout=10)

   if response.status_code == 200:
      return response.json().get("tag_name", "Unknown version")  # Extracts the version tag
   else:
      raise Exception(f"Failed to retrieve the latest release. Status code: {response.status_code}")


# Example usage:
if __name__ == "__main__":
   try:
      latest_version = get_latest_version()
      print(f"Latest NMMiner version: {latest_version}")
   except Exception as e:
      print(f"Error: {e}")
