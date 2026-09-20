#!/usr/bin/env python3
"""
5G Network Slicing Training Data Generator

This script generates synthetic training data for the 5G network slicing model.
It creates realistic traffic patterns for different scenarios including:
- Normal daily patterns
- Weekend patterns
- Special events (sports, concerts)
- Emergency scenarios
- IoT traffic surges

The data includes:
- Traffic load
- Time features (time of day, day of week)
- Slice allocation
- Slice utilization
- QoS metrics

Output is saved as CSV and NPY files for training the LSTM models.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import argparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TrainingDataGenerator:
    """Generator for 5G network slicing training data"""
    
    def __init__(self, args):
        """Initialize the data generator
        
        Args:
            args: Command line arguments
        """
        self.args = args
        self.num_samples = args.num_samples
        self.output_dir = args.output_dir
        self.visualize = args.visualize
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Define QoS thresholds for different slice types
        self.qos_thresholds = {
            'embb': 1.5,    # eMBB: High throughput, moderate latency
            'urllc': 1.2,   # URLLC: Ultra-low latency, high reliability
            'mmtc': 1.8     # mMTC: Massive connectivity
        }
        
        # Parameters for different scenarios
        self.scenarios = {
            'normal': {
                'traffic_base': 0.5,
                'traffic_amplitude': 0.3,
                'volatility': 0.1,
                'emergency_prob': 0.01,
                'special_event_prob': 0.05,
                'iot_surge_prob': 0.03
            },
            'weekend': {
                'traffic_base': 0.7,
                'traffic_amplitude': 0.4,
                'volatility': 0.15,
                'emergency_prob': 0.01,
                'special_event_prob': 0.2,
                'iot_surge_prob': 0.05
            },
            'emergency': {
                'traffic_base': 0.6,
                'traffic_amplitude': 0.2,
                'volatility': 0.3,
                'emergency_prob': 0.4,
                'special_event_prob': 0.05,
                'iot_surge_prob': 0.05
            },
            'smart_city': {
                'traffic_base': 0.6,
                'traffic_amplitude': 0.2,
                'volatility': 0.15,
                'emergency_prob': 0.02,
                'special_event_prob': 0.1,
                'iot_surge_prob': 0.3
            }
        }
        
        logger.info(f"Training data generator initialized for {self.num_samples} samples")
    
    def generate_data(self):
        """Generate the training dataset"""
        logger.info("Generating training data...")
        
        # Initialize arrays for features and targets
        X = np.zeros((self.num_samples, 11))  # 11 features
        y = np.zeros((self.num_samples, 3))   # 3 target values (slice allocations)
        
        # Generate a continuous timeline
        start_date = datetime(2025, 1, 1)
        dates = [start_date + timedelta(hours=i) for i in range(self.num_samples)]
        
        # Extract time features
        hour_of_day = np.array([d.hour / 24.0 for d in dates])
        day_of_week = np.array([d.weekday() / 6.0 for d in dates])
        is_weekend = np.array([1.0 if d.weekday() >= 5 else 0.0 for d in dates])
        
        # Generate base traffic pattern
        traffic_load = self._generate_traffic_pattern(dates)
        
        # Initialize slice allocations and utilizations
        slice_allocation = np.zeros((self.num_samples, 3))
        slice_utilization = np.zeros((self.num_samples, 3))
        
        # Generate client and base station counts
        client_count = 0.3 + 0.5 * traffic_load + 0.1 * np.random.randn(self.num_samples)
        bs_count = 0.5 + 0.1 * np.random.randn(self.num_samples)
        
        # Clip to valid ranges
        traffic_load = np.clip(traffic_load, 0.1, 2.0)
        client_count = np.clip(client_count, 0.1, 1.0)
        bs_count = np.clip(bs_count, 0.3, 1.0)
        
        # Generate events (emergencies, special events, IoT surges)
        events = self._generate_events(dates)
        
        # Simulate network operation and generate optimal allocations
        for i in range(self.num_samples):
            # Determine current scenario based on time and events
            if events['emergency'][i]:
                scenario = 'emergency'
            elif events['iot_surge'][i]:
                scenario = 'smart_city'
            elif is_weekend[i]:
                scenario = 'weekend'
            else:
                scenario = 'normal'
            
            # Get initial slice allocation (equal distribution)
            if i == 0:
                slice_allocation[i] = np.array([1/3, 1/3, 1/3])
            else:
                # Gradual change from previous allocation
                slice_allocation[i] = slice_allocation[i-1].copy()
            
            # Calculate utilization based on traffic and allocation
            for j in range(3):
                # Add small constant to avoid division by zero
                slice_utilization[i, j] = traffic_load[i] / (slice_allocation[i, j] + 0.01)
            
            # Add event effects to utilization
            if events['emergency'][i]:
                # Emergency increases URLLC and eMBB utilization
                slice_utilization[i, 1] += np.random.uniform(0.5, 1.0)  # URLLC
                slice_utilization[i, 0] += np.random.uniform(0.2, 0.5)  # eMBB
            
            if events['special_event'][i]:
                # Special events increase eMBB utilization
                slice_utilization[i, 0] += np.random.uniform(0.4, 0.8)  # eMBB
            
            if events['iot_surge'][i]:
                # IoT surges increase mMTC utilization
                slice_utilization[i, 2] += np.random.uniform(0.3, 0.7)  # mMTC
            
            # Clip utilization to valid range
            slice_utilization[i] = np.clip(slice_utilization[i], 0.1, 2.0)
            
            # Calculate optimal allocation based on current state
            # This simulates what a perfect model would predict
            optimal_allocation = self._calculate_optimal_allocation(
                traffic_load[i], 
                slice_utilization[i], 
                events['emergency'][i],
                events['special_event'][i],
                events['iot_surge'][i]
            )
            
            # Store features (X) and targets (y)
            X[i] = np.array([
                traffic_load[i],
                hour_of_day[i],
                day_of_week[i],
                slice_allocation[i, 0],  # eMBB allocation
                slice_allocation[i, 1],  # URLLC allocation
                slice_allocation[i, 2],  # mMTC allocation
                slice_utilization[i, 0],  # eMBB utilization
                slice_utilization[i, 1],  # URLLC utilization
                slice_utilization[i, 2],  # mMTC utilization
                client_count[i],
                bs_count[i]
            ])
            
            y[i] = optimal_allocation
            
            # Update allocation for next step
            if i < self.num_samples - 1:
                # Move 30% toward optimal allocation
                slice_allocation[i+1] = 0.7 * slice_allocation[i] + 0.3 * optimal_allocation
                # Ensure it sums to 1
                slice_allocation[i+1] = slice_allocation[i+1] / np.sum(slice_allocation[i+1])
        
        # Create DataFrame for easier analysis and CSV export
        df = pd.DataFrame({
            'timestamp': dates,
            'traffic_load': traffic_load,
            'hour_of_day': hour_of_day,
            'day_of_week': day_of_week,
            'is_weekend': is_weekend,
            'embb_allocation': slice_allocation[:, 0],
            'urllc_allocation': slice_allocation[:, 1],
            'mmtc_allocation': slice_allocation[:, 2],
            'embb_utilization': slice_utilization[:, 0],
            'urllc_utilization': slice_utilization[:, 1],
            'mmtc_utilization': slice_utilization[:, 2],
            'client_count': client_count,
            'bs_count': bs_count,
            'emergency': events['emergency'],
            'special_event': events['special_event'],
            'iot_surge': events['iot_surge'],
            'optimal_embb': y[:, 0],
            'optimal_urllc': y[:, 1],
            'optimal_mmtc': y[:, 2]
        })
        
        # Save the data
        self._save_data(X, y, df)
        
        # Visualize if requested
        if self.visualize:
            self._visualize_data(df)
        
        logger.info(f"Generated {self.num_samples} training samples")
        return X, y, df
    
    def _generate_traffic_pattern(self, dates):
        """Generate realistic traffic patterns based on time
        
        Args:
            dates: List of datetime objects
        
        Returns:
            numpy.ndarray: Traffic load for each time step
        """
        num_samples = len(dates)
        traffic = np.zeros(num_samples)
        
        # Extract hour and day of week
        hours = np.array([d.hour for d in dates])
        weekdays = np.array([d.weekday() for d in dates])
        
        for i in range(num_samples):
            hour = hours[i]
            weekday = weekdays[i]
            
            # Base daily pattern (higher during day, lower at night)
            if 8 <= hour < 20:  # Daytime
                base = 0.6 + 0.2 * np.sin((hour - 8) * np.pi / 12)
            else:  # Nighttime
                if hour < 8:
                    base = 0.3 + 0.1 * hour / 8
                else:  # hour >= 20
                    base = 0.3 + 0.1 * (24 - hour) / 4
            
            # Weekend effect
            if weekday >= 5:  # Weekend
                if 10 <= hour < 22:  # Different pattern on weekends
                    base = 0.7 + 0.2 * np.sin((hour - 10) * np.pi / 12)
                else:
                    base = 0.4
            
            # Add some randomness
            traffic[i] = base + 0.1 * np.random.randn()
        
        return traffic
    
    def _generate_events(self, dates):
        """Generate network events (emergencies, special events, IoT surges)
        
        Args:
            dates: List of datetime objects
        
        Returns:
            dict: Boolean arrays for different event types
        """
        num_samples = len(dates)
        
        # Extract hour and day of week
        hours = np.array([d.hour for d in dates])
        weekdays = np.array([d.weekday() for d in dates])
        
        # Initialize event arrays
        emergency = np.zeros(num_samples, dtype=bool)
        special_event = np.zeros(num_samples, dtype=bool)
        iot_surge = np.zeros(num_samples, dtype=bool)
        
        # Generate events
        for i in range(num_samples):
            hour = hours[i]
            weekday = weekdays[i]
            
            # Determine scenario based on time
            if weekday >= 5:  # Weekend
                scenario = 'weekend'
            else:
                scenario = 'normal'
            
            # Emergency events
            if np.random.random() < self.scenarios[scenario]['emergency_prob']:
                # Create emergency events that last for several hours
                duration = np.random.randint(1, 4)  # 1-3 hours
                for j in range(min(duration, num_samples - i)):
                    if i + j < num_samples:
                        emergency[i + j] = True
            
            # Special events (sports games, concerts, etc.)
            if np.random.random() < self.scenarios[scenario]['special_event_prob']:
                # Special events more likely in evenings and weekends
                if (weekday >= 5 and 12 <= hour < 23) or (weekday < 5 and 18 <= hour < 23):
                    duration = np.random.randint(2, 5)  # 2-4 hours
                    for j in range(min(duration, num_samples - i)):
                        if i + j < num_samples:
                            special_event[i + j] = True
            
            # IoT surges (smart city activities, sensor reporting, etc.)
            if np.random.random() < self.scenarios[scenario]['iot_surge_prob']:
                # IoT surges more common at specific times
                if hour in [0, 6, 12, 18]:  # Common reporting times
                    duration = np.random.randint(1, 3)  # 1-2 hours
                    for j in range(min(duration, num_samples - i)):
                        if i + j < num_samples:
                            iot_surge[i + j] = True
        
        return {
            'emergency': emergency,
            'special_event': special_event,
            'iot_surge': iot_surge
        }
    
    def _calculate_optimal_allocation(self, traffic, utilization, is_emergency, is_special_event, is_iot_surge):
        """Calculate optimal slice allocation based on current state
        
        This simulates what a perfect model would predict
        
        Args:
            traffic: Current traffic load
            utilization: Current slice utilization
            is_emergency: Whether there's an emergency event
            is_special_event: Whether there's a special event
            is_iot_surge: Whether there's an IoT surge
        
        Returns:
            numpy.ndarray: Optimal slice allocation
        """
        # Start with equal allocation
        allocation = np.array([1/3, 1/3, 1/3])
        
        # Adjust based on utilization (higher utilization -> more allocation)
        total_util = np.sum(utilization)
        if total_util > 0:
            # Normalize utilization
            util_factors = utilization / total_util
            # Mix with equal allocation (70% utilization-based, 30% equal)
            allocation = 0.7 * util_factors + 0.3 * allocation
        
        # Adjust for specific events
        if is_emergency:
            # Increase URLLC allocation during emergencies
            allocation[1] += 0.2  # URLLC
            allocation[0] -= 0.1  # eMBB
            allocation[2] -= 0.1  # mMTC
        
        if is_special_event:
            # Increase eMBB allocation during special events
            allocation[0] += 0.15  # eMBB
            allocation[2] -= 0.15  # mMTC
        
        if is_iot_surge:
            # Increase mMTC allocation during IoT surges
            allocation[2] += 0.15  # mMTC
            allocation[0] -= 0.15  # eMBB
        
        # Check for QoS violations and adjust
        for i, (slice_type, threshold) in enumerate(zip(['embb', 'urllc', 'mmtc'], 
                                                      [self.qos_thresholds['embb'], 
                                                       self.qos_thresholds['urllc'], 
                                                       self.qos_thresholds['mmtc']])):
            # If utilization is above threshold, increase allocation
            if utilization[i] > threshold:
                # Calculate how much to increase based on violation severity
                violation_factor = (utilization[i] - threshold) / threshold
                increase = min(0.1, violation_factor * 0.2)
                
                # Take from the least utilized slices
                other_indices = [j for j in range(3) if j != i]
                least_utilized_idx = other_indices[np.argmin(utilization[other_indices])]
                
                # Adjust allocations
                allocation[i] += increase
                allocation[least_utilized_idx] -= increase
        
        # Ensure allocations are within valid range
        allocation = np.clip(allocation, 0.1, 0.8)
        
        # Normalize to sum to 1
        allocation = allocation / np.sum(allocation)
        
        return allocation
    
    def _save_data(self, X, y, df):
        """Save the generated data
        
        Args:
            X: Feature matrix
            y: Target values
            df: DataFrame with all data
        """
        # Save as numpy arrays
        np.save(os.path.join(self.output_dir, 'X_train.npy'), X)
        np.save(os.path.join(self.output_dir, 'y_train.npy'), y)
        
        # Save as CSV
        df.to_csv(os.path.join(self.output_dir, 'training_data.csv'), index=False)
        
        # Save a sample for quick inspection
        df.head(100).to_csv(os.path.join(self.output_dir, 'training_data_sample.csv'), index=False)
        
        logger.info(f"Data saved to {self.output_dir}")
    
    def _visualize_data(self, df):
        """Create visualizations of the training data
        
        Args:
            df: DataFrame with all data
        """
        logger.info("Generating visualizations...")
        
        # Create figure with subplots
        fig, axs = plt.subplots(3, 2, figsize=(15, 12))
        fig.suptitle('5G Network Slicing Training Data', fontsize=16)
        
        # 1. Traffic load over time
        axs[0, 0].plot(df['timestamp'], df['traffic_load'])
        axs[0, 0].set_title('Traffic Load Over Time')
        axs[0, 0].set_xlabel('Time')
        axs[0, 0].set_ylabel('Traffic Load')
        axs[0, 0].grid(True)
        
        # Mark events
        emergency_times = df['timestamp'][df['emergency']]
        special_event_times = df['timestamp'][df['special_event']]
        iot_surge_times = df['timestamp'][df['iot_surge']]
        
        emergency_traffic = df['traffic_load'][df['emergency']]
        special_event_traffic = df['traffic_load'][df['special_event']]
        iot_surge_traffic = df['traffic_load'][df['iot_surge']]
        
        axs[0, 0].scatter(emergency_times, emergency_traffic, color='red', marker='o', label='Emergency')
        axs[0, 0].scatter(special_event_times, special_event_traffic, color='green', marker='s', label='Special Event')
        axs[0, 0].scatter(iot_surge_times, iot_surge_traffic, color='purple', marker='^', label='IoT Surge')
        axs[0, 0].legend()
        
        # 2. Slice utilization
        axs[0, 1].plot(df['timestamp'], df['embb_utilization'], label='eMBB', color='#FF6B6B')
        axs[0, 1].plot(df['timestamp'], df['urllc_utilization'], label='URLLC', color='#45B7D1')
        axs[0, 1].plot(df['timestamp'], df['mmtc_utilization'], label='mMTC', color='#FFBE0B')
        axs[0, 1].set_title('Slice Utilization Over Time')
        axs[0, 1].set_xlabel('Time')
        axs[0, 1].set_ylabel('Utilization')
        axs[0, 1].grid(True)
        axs[0, 1].legend()
        
        # Add threshold lines
        axs[0, 1].axhline(y=self.qos_thresholds['embb'], color='#FF6B6B', linestyle='--', alpha=0.7)
        axs[0, 1].axhline(y=self.qos_thresholds['urllc'], color='#45B7D1', linestyle='--', alpha=0.7)
        axs[0, 1].axhline(y=self.qos_thresholds['mmtc'], color='#FFBE0B', linestyle='--', alpha=0.7)
        
        # 3. Optimal slice allocation
        axs[1, 0].plot(df['timestamp'], df['optimal_embb'], label='eMBB', color='#FF6B6B')
        axs[1, 0].plot(df['timestamp'], df['optimal_urllc'], label='URLLC', color='#45B7D1')
        axs[1, 0].plot(df['timestamp'], df['optimal_mmtc'], label='mMTC', color='#FFBE0B')
        axs[1, 0].set_title('Optimal Slice Allocation Over Time')
        axs[1, 0].set_xlabel('Time')
        axs[1, 0].set_ylabel('Allocation')
        axs[1, 0].grid(True)
        axs[1, 0].legend()
        
        # 4. Daily traffic pattern
        # Group by hour and calculate mean
        hourly_traffic = df.groupby(df['timestamp'].dt.hour)['traffic_load'].mean()
        axs[1, 1].plot(hourly_traffic.index, hourly_traffic.values)
        axs[1, 1].set_title('Average Traffic by Hour of Day')
        axs[1, 1].set_xlabel('Hour of Day')
        axs[1, 1].set_ylabel('Average Traffic')
        axs[1, 1].set_xticks(range(0, 24, 2))
        axs[1, 1].grid(True)
        
        # 5. Weekly traffic pattern
        # Group by day of week and calculate mean
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekly_traffic = df.groupby(df['timestamp'].dt.weekday)['traffic_load'].mean()
        axs[2, 0].bar(day_names, weekly_traffic.values)
        axs[2, 0].set_title('Average Traffic by Day of Week')
        axs[2, 0].set_xlabel('Day of Week')
        axs[2, 0].set_ylabel('Average Traffic')
        axs[2, 0].grid(True)
        
        # 6. Allocation vs. Utilization scatter plot
        # Create a scatter plot for each slice type
        axs[2, 1].scatter(df['embb_utilization'], df['optimal_embb'], 
                         alpha=0.5, label='eMBB', color='#FF6B6B')
        axs[2, 1].scatter(df['urllc_utilization'], df['optimal_urllc'], 
                         alpha=0.5, label='URLLC', color='#45B7D1')
        axs[2, 1].scatter(df['mmtc_utilization'], df['optimal_mmtc'], 
                         alpha=0.5, label='mMTC', color='#FFBE0B')
        axs[2, 1].set_title('Optimal Allocation vs. Utilization')
        axs[2, 1].set_xlabel('Utilization')
        axs[2, 1].set_ylabel('Optimal Allocation')
        axs[2, 1].grid(True)
        axs[2, 1].legend()
        
        # Save the figure
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'training_data_visualization.png'))
        plt.close()
        
        # Create additional visualizations
        
        # 1. Allocation during different events
        fig, axs = plt.subplots(1, 3, figsize=(18, 5))
        
        # Emergency events
        if sum(df['emergency']) > 0:
            emergency_data = df[df['emergency']]
            axs[0].bar(['eMBB', 'URLLC', 'mMTC'], 
                     [emergency_data['optimal_embb'].mean(), 
                      emergency_data['optimal_urllc'].mean(), 
                      emergency_data['optimal_mmtc'].mean()])
            axs[0].set_title('Average Allocation During Emergencies')
            axs[0].set_ylabel('Allocation')
            axs[0].grid(True)
        
        # Special events
        if sum(df['special_event']) > 0:
            special_data = df[df['special_event']]
            axs[1].bar(['eMBB', 'URLLC', 'mMTC'], 
                     [special_data['optimal_embb'].mean(), 
                      special_data['optimal_urllc'].mean(), 
                      special_data['optimal_mmtc'].mean()])
            axs[1].set_title('Average Allocation During Special Events')
            axs[1].set_ylabel('Allocation')
            axs[1].grid(True)
        
        # IoT surges
        if sum(df['iot_surge']) > 0:
            iot_data = df[df['iot_surge']]
            axs[2].bar(['eMBB', 'URLLC', 'mMTC'], 
                     [iot_data['optimal_embb'].mean(), 
                      iot_data['optimal_urllc'].mean(), 
                      iot_data['optimal_mmtc'].mean()])
            axs[2].set_title('Average Allocation During IoT Surges')
            axs[2].set_ylabel('Allocation')
            axs[2].grid(True)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'event_allocations.png'))
        plt.close()
        
        logger.info("Visualizations saved to output directory")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='5G Network Slicing Training Data Generator')
    
    parser.add_argument('--num_samples', type=int, default=8760,
                        help='Number of samples to generate (default: 8760, one year hourly)')
    
    parser.add_argument('--output_dir', type=str, default='data/training',
                        help='Directory to save output files')
    
    parser.add_argument('--visualize', action='store_true',
                        help='Generate visualizations of the data')
    
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Create and run the generator
    generator = TrainingDataGenerator(args)
    X, y, df = generator.generate_data()
    
    # Print summary statistics
    print("\nTraining Data Summary:")
    print(f"Number of samples: {len(df)}")
    print(f"Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"Emergency events: {sum(df['emergency'])} ({sum(df['emergency'])/len(df)*100:.1f}%)")
    print(f"Special events: {sum(df['special_event'])} ({sum(df['special_event'])/len(df)*100:.1f}%)")
    print(f"IoT surges: {sum(df['iot_surge'])} ({sum(df['iot_surge'])/len(df)*100:.1f}%)")
    
    print("\nAverage optimal allocations:")
    print(f"  eMBB: {df['optimal_embb'].mean():.4f}")
    print(f"  URLLC: {df['optimal_urllc'].mean():.4f}")
    print(f"  mMTC: {df['optimal_mmtc'].mean():.4f}")
    
    print("\nData saved to:", args.output_dir) 