import math
from collections import defaultdict

class Distributor:
    def __init__(self, name, distribution, *dist_params, divide_scale=1):
        self.name = name
        self.distribution = distribution
        self.dist_params = dist_params
        self.divide_scale = divide_scale

    def generate(self):
        return self.distribution(*self.dist_params)

    def generate_scaled(self):
        try:
            return self.distribution(*self.dist_params)
        except (ValueError, TypeError) as e:
            # Fallback to a safer default
            import random
            return random.random() * 100

    def generate_movement(self):
        try:
            # Handle specific distributions that require integers
            if self.distribution.__name__ in ('randrange', 'randint'):
                # Make sure parameters are integers for these functions
                int_params = [int(param) for param in self.dist_params]
                x = self.distribution(*int_params) / self.divide_scale
                y = self.distribution(*int_params) / self.divide_scale
            else:
                # For other distributions, use parameters as is
                x = self.distribution(*self.dist_params) / self.divide_scale
                y = self.distribution(*self.dist_params) / self.divide_scale
            
            return x, y
        except (ValueError, TypeError) as e:
            # Fallback to safer defaults if there's an error
            print(f"Error generating movement with {self.distribution.__name__}: {str(e)}")
            # Use a safer method
            import random
            x = (random.random() * 100) / self.divide_scale 
            y = (random.random() * 100) / self.divide_scale
            return x, y

    def __str__(self):
        return f'[{self.name}: {self.distribution.__name__}: {self.dist_params}]'