#!/usr/bin/env python3
"""
5G Slice Allocation Analyzer

This tool provides detailed analysis and visualization of how AI models 
allocate 5G network slices under different scenarios.
"""

import os
import sys
import numpy as np
import json
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import argparse
from datetime import datetime
import pandas as pd
import seaborn as sns

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from slicesim.ai.lstm_predictor import SliceAllocationPredictor
from slicesim.ai.dqn_classifier import TrafficClassifier
from slicesim.slice_optimization import SliceOptimizer

class SliceAnalyzer:
    """Analyzes and visualizes slice allocation decisions"""
    
    def __init__(self, results_dir='results'):
        """Initialize the slice analyzer
        
        Args:
            results_dir (str): Directory containing results
        """
        self.results_dir = results_dir
        self.ai_optimizer = SliceOptimizer(use_ai=True)
        self.traditional_optimizer = SliceOptimizer(use_ai=False)
        
        # Dictionary to explain slicing decisions for each scenario
        self.scenario_explanations = {
            'baseline': "Baseline traffic conditions with moderate fluctuations.",
            'dynamic': "Rapidly changing traffic patterns requiring frequent adaptation.",
            'emergency': "Prioritizes URLLC traffic for critical communications.",
            'smart_city': "High mMTC traffic from many IoT devices."
        }
        
        # Dictionary to explain slice types
        self.slice_explanations = {
            'eMBB': "Enhanced Mobile Broadband - High bandwidth for video streaming, AR/VR",
            'URLLC': "Ultra-Reliable Low Latency Communication - Mission-critical applications",
            'mMTC': "Massive Machine Type Communication - IoT devices, sensors"
        }
        
        # Factors that influence slice allocation
        self.allocation_factors = {
            'traffic_load': "Overall network congestion level",
            'time_of_day': "Time-based traffic patterns",
            'utilization': "Current resource usage per slice",
            'slice_type': "Specific slice requirements and priorities"
        }
    
    def load_results(self, scenario):
        """Load results for a specific scenario
        
        Args:
            scenario (str): Scenario name
            
        Returns:
            dict: Results data
        """
        # Find the most recent result file for this scenario
        result_files = [f for f in os.listdir(self.results_dir) 
                        if f.startswith(f"{scenario}_results_") and f.endswith('.json')]
        
        if not result_files:
            raise FileNotFoundError(f"No results found for scenario: {scenario}")
        
        # Sort by timestamp (newest first)
        result_files.sort(reverse=True)
        result_file = os.path.join(self.results_dir, result_files[0])
        
        # Load results
        with open(result_file, 'r') as f:
            results = json.load(f)
        
        return results
    
    def generate_mock_network_state(self, scenario, time_point):
        """Generate a mock network state for demonstration
        
        Args:
            scenario (str): Scenario name
            time_point (int): Time point
            
        Returns:
            dict: Mock network state
        """
        # Generate base state
        state = {
            'time': time_point,
            'clients': [],
            'base_stations': []
        }
        
        # Configure scenario-specific parameters
        if scenario == 'baseline':
            traffic_factor = 0.7 + 0.2 * np.sin(time_point / 10)
            embb_clients = 30
            urllc_clients = 20
            mmtc_clients = 25
        elif scenario == 'dynamic':
            traffic_factor = 0.4 + 0.5 * np.sin(time_point / 5)
            embb_clients = 25 + int(10 * np.sin(time_point / 7))
            urllc_clients = 15 + int(10 * np.cos(time_point / 5))
            mmtc_clients = 20 + int(15 * np.sin(time_point / 9))
        elif scenario == 'emergency':
            traffic_factor = 0.9
            embb_clients = 15
            urllc_clients = 40
            mmtc_clients = 10
        else:  # smart_city
            traffic_factor = 0.8
            embb_clients = 20
            urllc_clients = 15
            mmtc_clients = 50
        
        # Create base stations
        for bs_id in range(1, 3):
            base_station = {
                'id': f'bs{bs_id}',
                'capacity': 10,
                'location': [bs_id * 5, bs_id * 5],
                'slice_usage': {
                    'eMBB': 0.4 * traffic_factor * (1 + 0.2 * np.random.randn()),
                    'URLLC': 0.3 * traffic_factor * (1 + 0.2 * np.random.randn()),
                    'mMTC': 0.3 * traffic_factor * (1 + 0.2 * np.random.randn())
                },
                'slice_allocation': {
                    'eMBB': 0.33,
                    'URLLC': 0.33,
                    'mMTC': 0.34
                }
            }
            state['base_stations'].append(base_station)
        
        # Create clients
        client_id = 1
        
        # Add eMBB clients
        for i in range(embb_clients):
            bs_id = 'bs1' if i < embb_clients // 2 else 'bs2'
            client = {
                'id': client_id,
                'slice': 'eMBB',
                'base_station': bs_id,
                'data_rate': 1.5 * traffic_factor * (1 + 0.2 * np.random.randn()),
                'active': np.random.random() < 0.8
            }
            state['clients'].append(client)
            client_id += 1
        
        # Add URLLC clients
        for i in range(urllc_clients):
            bs_id = 'bs1' if i < urllc_clients // 2 else 'bs2'
            client = {
                'id': client_id,
                'slice': 'URLLC',
                'base_station': bs_id,
                'data_rate': 0.8 * traffic_factor * (1 + 0.2 * np.random.randn()),
                'active': np.random.random() < 0.9  # URLLC has higher activity
            }
            state['clients'].append(client)
            client_id += 1
        
        # Add mMTC clients
        for i in range(mmtc_clients):
            bs_id = 'bs1' if i < mmtc_clients // 2 else 'bs2'
            client = {
                'id': client_id,
                'slice': 'mMTC',
                'base_station': bs_id,
                'data_rate': 0.3 * traffic_factor * (1 + 0.2 * np.random.randn()),
                'active': np.random.random() < 0.7
            }
            state['clients'].append(client)
            client_id += 1
        
        return state
    
    def analyze_slice_allocation(self, scenario, time_point=None):
        """Analyze slice allocation for a specific scenario
        
        Args:
            scenario (str): Scenario name
            time_point (int, optional): Specific time point to analyze
            
        Returns:
            dict: Analysis results
        """
        # Generate a representative network state
        if time_point is None:
            time_point = 15  # Default time point
        
        network_state = self.generate_mock_network_state(scenario, time_point)
        
        # Get optimization results
        ai_allocation = self.ai_optimizer.optimize_slices(network_state)
        traditional_allocation = self.traditional_optimizer.optimize_slices(network_state)
        
        # Extract features for analysis
        features = self.ai_optimizer._extract_features(network_state)
        
        # Analyze first base station for simplicity
        bs_id = network_state['base_stations'][0]['id']
        bs_features = [f for f in features['base_stations'] if f['id'] == bs_id][0]
        
        # Extract current metrics
        current_allocation = bs_features['slice_allocation']
        slice_usage = bs_features['slice_usage']
        
        # Calculate utilization ratios
        utilization = {}
        for slice_type in ['eMBB', 'URLLC', 'mMTC']:
            usage = slice_usage.get(slice_type, 0)
            allocation = current_allocation.get(slice_type, 0.33)
            if allocation > 0:
                utilization[slice_type] = usage / allocation
            else:
                utilization[slice_type] = 0
        
        # Prepare input features for AI models to analyze decisions
        time_of_day = features['global']['time'] % 24 / 24
        day_of_week = (features['global']['time'] // 24) % 7 / 6
        
        # Calculate traffic load
        total_capacity = bs_features['capacity']
        total_usage = sum(slice_usage.values())
        traffic_load = min(2.0, total_usage / max(0.001, total_capacity))
        
        # Input for AI models
        model_input = np.array([
            traffic_load,
            time_of_day,
            day_of_week,
            current_allocation.get('eMBB', 0.33),
            current_allocation.get('URLLC', 0.33),
            current_allocation.get('mMTC', 0.34),
            utilization.get('eMBB', 0),
            utilization.get('URLLC', 0),
            utilization.get('mMTC', 0),
            bs_features['client_count'] / 20,
            len(features['base_stations']) / 5
        ])
        
        # Get LSTM prediction
        lstm_allocation = self.ai_optimizer.lstm_model.predict(model_input)[0]
        
        # Get DQN classification
        dqn_class, dqn_probs = self.ai_optimizer.dqn_model.classify(model_input)
        
        # Assemble results
        analysis = {
            'scenario': scenario,
            'time_point': time_point,
            'base_station': bs_id,
            'traffic_load': traffic_load,
            'time_of_day': time_of_day * 24,  # Convert back to hours
            'current_allocation': current_allocation,
            'slice_usage': slice_usage,
            'utilization': utilization,
            'client_counts': {
                'eMBB': len([c for c in network_state['clients'] if c['slice'] == 'eMBB' and c['base_station'] == bs_id]),
                'URLLC': len([c for c in network_state['clients'] if c['slice'] == 'URLLC' and c['base_station'] == bs_id]),
                'mMTC': len([c for c in network_state['clients'] if c['slice'] == 'mMTC' and c['base_station'] == bs_id])
            },
            'traditional_allocation': traditional_allocation[bs_id],
            'ai_allocation': ai_allocation[bs_id],
            'lstm_raw_allocation': {
                'eMBB': float(lstm_allocation[0]),
                'URLLC': float(lstm_allocation[1]),
                'mMTC': float(lstm_allocation[2])
            },
            'dqn_classification': {
                'class': self.ai_optimizer.dqn_model.get_class_name(dqn_class[0]),
                'probabilities': {
                    'eMBB': float(dqn_probs[0][0]),
                    'URLLC': float(dqn_probs[0][1]),
                    'mMTC': float(dqn_probs[0][2])
                }
            }
        }
        
        # Generate explanations
        analysis['explanations'] = self._generate_explanations(analysis)
        
        return analysis
    
    def _generate_explanations(self, analysis):
        """Generate explanations for the allocation decisions
        
        Args:
            analysis (dict): Analysis data
            
        Returns:
            dict: Explanations
        """
        scenario = analysis['scenario']
        traffic_load = analysis['traffic_load']
        time_of_day = analysis['time_of_day']
        utilization = analysis['utilization']
        client_counts = analysis['client_counts']
        
        # Scenario-specific explanation
        scenario_explanation = self.scenario_explanations.get(
            scenario, 
            "Custom scenario with specific traffic patterns."
        )
        
        # Traffic load explanation
        if traffic_load < 0.5:
            traffic_explanation = "Low traffic load allows for balanced slice allocation."
        elif traffic_load < 1.0:
            traffic_explanation = "Moderate traffic requires optimization based on usage patterns."
        else:
            traffic_explanation = "High traffic load requires prioritizing slices with highest demand."
        
        # Time-based explanation
        if 0 <= time_of_day < 6 or 22 <= time_of_day <= 24:
            time_explanation = "Night-time traffic typically has lower eMBB and higher mMTC demands."
        elif 6 <= time_of_day < 9 or 17 <= time_of_day < 22:
            time_explanation = "Peak commuting hours often see increased URLLC traffic."
        else:
            time_explanation = "Business hours typically have higher eMBB demands."
        
        # Utilization-based explanation
        slice_explanations = {}
        for slice_type, util in utilization.items():
            if util < 0.3:
                slice_explanations[slice_type] = f"{slice_type} is under-utilized (utilization: {util:.2f})."
            elif util < 0.8:
                slice_explanations[slice_type] = f"{slice_type} has good utilization (utilization: {util:.2f})."
            else:
                slice_explanations[slice_type] = f"{slice_type} is heavily utilized (utilization: {util:.2f})."
        
        # Client-based explanation
        total_clients = sum(client_counts.values())
        client_explanation = "Client distribution: "
        if total_clients > 0:
            client_explanation += ", ".join([
                f"{slice_type}: {count} ({count/total_clients*100:.1f}%)" 
                for slice_type, count in client_counts.items()
            ])
        else:
            client_explanation += "No active clients."
        
        # AI decision reasoning
        ai_allocation = analysis['ai_allocation']
        traditional_allocation = analysis['traditional_allocation']
        dqn_class = analysis['dqn_classification']['class']
        
        # Major difference identification
        differences = {}
        for slice_type in ai_allocation:
            diff = ai_allocation[slice_type] - traditional_allocation[slice_type]
            differences[slice_type] = diff * 100  # Convert to percentage points
        
        # Find the slice with the largest positive difference (AI allocates more)
        max_increase = max(differences.items(), key=lambda x: x[1])
        max_decrease = min(differences.items(), key=lambda x: x[1])
        
        # AI decision summary
        if abs(max_increase[1]) > 10 or abs(max_decrease[1]) > 10:
            decision_summary = (
                f"AI significantly adjusted the slice allocation compared to traditional methods: "
                f"{max_increase[0]} increased by {max_increase[1]:.1f}%, "
                f"{max_decrease[0]} decreased by {abs(max_decrease[1]):.1f}%. "
                f"DQN classified the dominant traffic pattern as {dqn_class}."
            )
        else:
            decision_summary = (
                f"AI made minor adjustments to the slice allocation: "
                f"largest change was {max(abs(max_increase[1]), abs(max_decrease[1])):.1f}%. "
                f"DQN classified the dominant traffic pattern as {dqn_class}."
            )
        
        return {
            'scenario': scenario_explanation,
            'traffic': traffic_explanation,
            'time': time_explanation,
            'slices': slice_explanations,
            'clients': client_explanation,
            'decision': decision_summary
        }
    
    def visualize_analysis(self, analysis, save_path=None):
        """Visualize the analysis results
        
        Args:
            analysis (dict): Analysis data
            save_path (str, optional): Path to save the visualization
        """
        scenario = analysis['scenario']
        
        # Create figure with gridspec for layout
        fig = plt.figure(figsize=(15, 10))
        gs = GridSpec(3, 3, figure=fig)
        
        # Title and scenario info
        ax_title = fig.add_subplot(gs[0, :])
        ax_title.axis('off')
        
        title_text = (
            f"5G Network Slice Allocation Analysis - {scenario.title()} Scenario\n"
            f"Time: {analysis['time_point']}, Traffic Load: {analysis['traffic_load']:.2f}, "
            f"Time of Day: {analysis['time_of_day']:.1f} hours"
        )
        ax_title.text(0.5, 0.7, title_text, fontsize=16, ha='center', fontweight='bold')
        
        # Add scenario explanation
        ax_title.text(0.5, 0.3, analysis['explanations']['scenario'], fontsize=12, ha='center', style='italic')
        
        # Current allocation and usage
        ax_current = fig.add_subplot(gs[1, 0])
        self._plot_allocation_comparison(
            ax_current, 
            analysis['current_allocation'], 
            analysis['slice_usage'],
            title="Current Allocation vs. Usage"
        )
        
        # Traditional vs. AI allocation
        ax_comparison = fig.add_subplot(gs[1, 1])
        self._plot_allocation_comparison(
            ax_comparison, 
            analysis['traditional_allocation'], 
            analysis['ai_allocation'],
            title="Traditional vs. AI Allocation"
        )
        
        # DQN classification results
        ax_dqn = fig.add_subplot(gs[1, 2])
        self._plot_dqn_results(ax_dqn, analysis['dqn_classification'])
        
        # Utilization and Client Distribution as a heatmap
        ax_metrics = fig.add_subplot(gs[2, 0])
        self._plot_metrics_heatmap(ax_metrics, analysis)
        
        # Explanations
        ax_explain = fig.add_subplot(gs[2, 1:])
        self._add_explanations(ax_explain, analysis['explanations'])
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path)
            print(f"Analysis visualization saved to {save_path}")
        
        plt.show()
    
    def _plot_allocation_comparison(self, ax, allocation1, allocation2, title):
        """Plot comparison between two allocations
        
        Args:
            ax: Matplotlib axis
            allocation1 (dict): First allocation
            allocation2 (dict): Second allocation
            title (str): Plot title
        """
        labels = list(allocation1.keys())
        x = np.arange(len(labels))
        width = 0.35
        
        # Extract values, ensuring they're in the same order as labels
        values1 = [allocation1.get(label, 0) for label in labels]
        
        # Check if allocation2 is a dictionary or just values
        if isinstance(allocation2, dict):
            values2 = [allocation2.get(label, 0) for label in labels]
        else:
            values2 = allocation2
        
        # Create bars
        ax.bar(x - width/2, values1, width, label='Allocation 1')
        ax.bar(x + width/2, values2, width, label='Allocation 2')
        
        # Add labels and title
        ax.set_ylabel('Proportion')
        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylim(0, 1)
        ax.legend()
        
        # Add value labels
        for i, v in enumerate(values1):
            ax.text(i - width/2, v + 0.02, f'{v:.2f}', ha='center')
        
        for i, v in enumerate(values2):
            ax.text(i + width/2, v + 0.02, f'{v:.2f}', ha='center')
    
    def _plot_dqn_results(self, ax, dqn_classification):
        """Plot DQN classification results
        
        Args:
            ax: Matplotlib axis
            dqn_classification (dict): DQN classification results
        """
        probabilities = dqn_classification['probabilities']
        labels = list(probabilities.keys())
        values = [probabilities[label] for label in labels]
        
        # Create bars with colors
        colors = ['#2196F3', '#4CAF50', '#FFC107']
        bars = ax.bar(labels, values, color=colors)
        
        # Highlight the classified class
        class_idx = labels.index(dqn_classification['class'])
        bars[class_idx].set_color('#F44336')
        
        # Add a line for random guess
        ax.axhline(y=0.33, color='red', linestyle='--', alpha=0.5, label='Random guess')
        
        # Add labels and title
        ax.set_ylabel('Probability')
        ax.set_title(f"Traffic Classification: {dqn_classification['class']}")
        ax.set_ylim(0, 1)
        
        # Add value labels
        for i, v in enumerate(values):
            ax.text(i, v + 0.02, f'{v:.2f}', ha='center')
    
    def _plot_metrics_heatmap(self, ax, analysis):
        """Plot metrics as a heatmap
        
        Args:
            ax: Matplotlib axis
            analysis (dict): Analysis data
        """
        # Prepare data
        metrics = {
            'Utilization': analysis['utilization'],
            'Client Count': {k: v / max(1, sum(analysis['client_counts'].values())) 
                             for k, v in analysis['client_counts'].items()}
        }
        
        # Convert to DataFrame for heatmap
        data = []
        for metric, values in metrics.items():
            for slice_type, value in values.items():
                data.append({
                    'Metric': metric,
                    'Slice': slice_type,
                    'Value': value
                })
        
        df = pd.DataFrame(data)
        df_pivot = df.pivot(index='Metric', columns='Slice', values='Value')
        
        # Create heatmap
        sns.heatmap(df_pivot, annot=True, cmap='YlGnBu', fmt='.2f', ax=ax)
        ax.set_title('Metrics by Slice Type')
    
    def _add_explanations(self, ax, explanations):
        """Add explanations to the plot
        
        Args:
            ax: Matplotlib axis
            explanations (dict): Explanation texts
        """
        ax.axis('off')
        
        # Title
        ax.text(0, 1, "AI Reasoning Analysis", fontsize=14, fontweight='bold')
        
        # Traffic explanation
        ax.text(0, 0.9, "Traffic Analysis:", fontsize=12, fontweight='bold')
        ax.text(0, 0.85, explanations['traffic'], fontsize=10)
        
        # Time explanation
        ax.text(0, 0.75, "Time Pattern Analysis:", fontsize=12, fontweight='bold')
        ax.text(0, 0.7, explanations['time'], fontsize=10)
        
        # Slice explanations
        ax.text(0, 0.6, "Slice Utilization Analysis:", fontsize=12, fontweight='bold')
        y_pos = 0.55
        for slice_type, explanation in explanations['slices'].items():
            ax.text(0, y_pos, explanation, fontsize=10)
            y_pos -= 0.05
        
        # Client explanation
        ax.text(0, 0.35, "Client Distribution:", fontsize=12, fontweight='bold')
        ax.text(0, 0.3, explanations['clients'], fontsize=10)
        
        # Decision summary
        ax.text(0, 0.2, "AI Decision Summary:", fontsize=12, fontweight='bold')
        ax.text(0, 0.15, explanations['decision'], fontsize=10, wrap=True)
    
    def compare_scenarios(self, save_dir=None):
        """Compare slice allocation across different scenarios
        
        Args:
            save_dir (str, optional): Directory to save visualizations
        """
        scenarios = ['baseline', 'dynamic', 'emergency', 'smart_city']
        results = []
        
        for scenario in scenarios:
            analysis = self.analyze_slice_allocation(scenario)
            results.append(analysis)
            
            # Visualize each scenario
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, f"{scenario}_analysis.png")
                self.visualize_analysis(analysis, save_path)
        
        # Create comparison visualization
        self._visualize_scenario_comparison(results, 
                                          save_path=os.path.join(save_dir, "scenario_comparison.png") if save_dir else None)
    
    def _visualize_scenario_comparison(self, analyses, save_path=None):
        """Visualize comparison between scenarios
        
        Args:
            analyses (list): List of analysis results
            save_path (str, optional): Path to save visualization
        """
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        axes = axes.flatten()
        
        for i, analysis in enumerate(analyses):
            scenario = analysis['scenario']
            ax = axes[i]
            
            # Extract allocations
            trad_alloc = analysis['traditional_allocation']
            ai_alloc = analysis['ai_allocation']
            
            # Calculate differences
            differences = {}
            for slice_type in ai_alloc:
                differences[slice_type] = (ai_alloc[slice_type] - trad_alloc[slice_type]) * 100  # percentage points
            
            # Plot differences
            labels = list(differences.keys())
            values = [differences[label] for label in labels]
            
            # Use colors based on positive/negative
            colors = ['#4CAF50' if v > 0 else '#F44336' for v in values]
            
            ax.bar(labels, values, color=colors)
            
            # Add a zero line
            ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
            
            # Add labels and title
            ax.set_ylabel('Percentage Point Difference')
            ax.set_title(f"{scenario.title()} Scenario")
            
            # Add value labels
            for j, v in enumerate(values):
                ax.text(j, v + np.sign(v)*1, f'{v:.1f}%', ha='center')
            
            # Add DQN classification
            dqn_class = analysis['dqn_classification']['class']
            ax.text(0.5, 0.9, f"Dominant Traffic: {dqn_class}", 
                   transform=ax.transAxes, ha='center', fontweight='bold')
        
        plt.suptitle("AI vs. Traditional Slice Allocation Across Scenarios", fontsize=16)
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path)
            print(f"Scenario comparison saved to {save_path}")
        
        plt.show()


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="5G Slice Allocation Analyzer")
    parser.add_argument('--scenario', type=str, default='all',
                        choices=['all', 'baseline', 'dynamic', 'emergency', 'smart_city'],
                        help='Scenario to analyze')
    parser.add_argument('--time', type=int, default=15,
                        help='Time point to analyze')
    parser.add_argument('--save-dir', type=str, default='analysis_results',
                        help='Directory to save results')
    
    args = parser.parse_args()
    
    analyzer = SliceAnalyzer(results_dir='results')
    
    if args.scenario == 'all':
        analyzer.compare_scenarios(save_dir=args.save_dir)
    else:
        analysis = analyzer.analyze_slice_allocation(args.scenario, args.time)
        save_path = os.path.join(args.save_dir, f"{args.scenario}_analysis.png") if args.save_dir else None
        analyzer.visualize_analysis(analysis, save_path)


if __name__ == "__main__":
    main() 