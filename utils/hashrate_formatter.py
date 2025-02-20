import re


class HashrateFormatter:
   """
   A class to handle the conversion and formatting of hash rate values.
   """
   # Define unit multipliers
   multipliers = {
      "H/S": 1,
      "KH/S": 1E3,
      "MH/S": 1E6,
      "GH/S": 1E9,
      "TH/S": 1E12,
      "PH/S": 1E15,
      "EH/S": 1E18,
      "ZH/S": 1E21,
      "YH/S": 1E24,
   }

   units = ["H/s", "KH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s", "ZH/s", "YH/s"]

   def __init__(self, value=None):
      """
      Initializes the object with an optional initial value (in hashes per second).
      """
      self.value = value

   def convert_hashrate(self, hashrate_str):
      """
      Convert a hashrate string (e.g., '10KH/s', '1.5GH/s') to the number of hashes per second.

      Args:
          hashrate_str (str): The hashrate string to convert.

      Returns:
          float: The hashrate in hashes per second.

      Raises:
          ValueError: If the input string is not in a valid format.
      """
      # Extract the number and unit using regex (fullmatch to match the whole string)
      match = re.fullmatch(r"([\d.]+)\s*([KMGTPEZY]?[Hh]?[\/s]+)", hashrate_str)
      if not match:
         raise ValueError(f'Invalid hashrate format: `{hashrate_str}`')

      value, unit = match.groups()
      value = float(value)

      # Convert unit to uppercase for case-insensitive matching
      unit = unit.upper()

      if unit not in self.multipliers:
         raise ValueError(f'Invalid unit in hashrate: `{unit}`')

      # Set the value
      self.value = value * self.multipliers[unit]
      return self.value

   def format_hashrate(self, hashrate):
      """
      Format a hashrate value into a human-readable string with appropriate units (e.g., '10.00KH/s').

      Returns:
          str: The formatted hashrate string.
      """
      # Find the correct unit by iterating through the units list
      index = 0
      value = hashrate
      while value >= 1000 and index < len(self.units) - 1:
         value /= 1000
         index += 1

      return f"{value:.2f}{self.units[index]}"


if __name__ == "__main__":
   # Example Usage:
   # 1. Create an instance
   hasher = HashrateFormatter()

   # 2. Convert a string into hash rate
   hasher.convert_hashrate("2.5GH/s")
   print(hasher.value)  # Output: 2500000000.0

   # 3. Format the converted value
   formatted_value = hasher.format_hashrate()
   print(formatted_value)  # Output: "2.50GH/s"
