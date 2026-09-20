import simpy

class Slice:
    def __init__(self, name, capacity, env, connected_users=0):
        """Initialize a network slice
        
        Args:
            name (str): Name of the slice
            capacity (float): Total capacity of the slice
            env (simpy.Environment): Simulation environment
            connected_users (int): Initial number of connected users
        """
        self.name = name
        self.connected_users = connected_users
        
        # Default QoS parameters based on slice type
        if "eMBB" in name:
            self.delay_tolerance = 100    # Higher delay tolerance (ms)
            self.qos_class = 3            # Lower priority
            self.bandwidth_guaranteed = capacity * 0.1  # 10% guaranteed
            self.bandwidth_max = capacity * 0.8         # 80% maximum
        elif "URLLC" in name:
            self.delay_tolerance = 1      # Very low delay tolerance (ms)
            self.qos_class = 1            # Highest priority
            self.bandwidth_guaranteed = capacity * 0.3  # 30% guaranteed
            self.bandwidth_max = capacity * 0.5         # 50% maximum
        elif "mMTC" in name:
            self.delay_tolerance = 50     # Medium delay tolerance (ms)
            self.qos_class = 4            # Lowest priority
            self.bandwidth_guaranteed = capacity * 0.05 # 5% guaranteed
            self.bandwidth_max = capacity * 0.3         # 30% maximum
        else:  # voice
            self.delay_tolerance = 20     # Low delay tolerance (ms)
            self.qos_class = 2            # High priority
            self.bandwidth_guaranteed = capacity * 0.2  # 20% guaranteed
            self.bandwidth_max = capacity * 0.4         # 40% maximum
            
        # Create simpy resource container for capacity management
        self.capacity = simpy.Container(env, capacity, init=capacity)
    
    def get_utilization(self):
        """Get current utilization percentage of this slice"""
        return 1.0 - (self.capacity.level / self.capacity.capacity)
    
    def get_consumable_share(self):
        """Get the amount that can be consumed per user"""
        if self.connected_users <= 0:
            return min(self.capacity.level, self.bandwidth_max)
        else:
            return min(self.capacity.level/self.connected_users, self.bandwidth_max)

    def is_avaliable(self):
        """Check if the slice has enough capacity for another user"""
        if self.capacity.level <= 0:
            return False
            
        real_cap = min(self.capacity.level, self.bandwidth_max)
        bandwidth_next = real_cap / (self.connected_users + 1)
        
        return bandwidth_next >= self.bandwidth_guaranteed

    def __str__(self):
        return f'{self.name:<10} cap={self.capacity.capacity:<5} used={self.capacity.capacity-self.capacity.level:<5} ({self.get_utilization()*100:.1f}%)'
