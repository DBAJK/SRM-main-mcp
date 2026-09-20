from statistics import mean

from matplotlib import gridspec
import matplotlib.animation as animation
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter, FuncFormatter
import matplotlib.patches as mpatches
import randomcolor
import numpy as np
import math
import time

from .utils import format_bps


class Graph:
    def __init__(self, base_stations, clients, xlim, map_limits,
                 output_dpi=500, scatter_size=15, output_filename='output.png'):
        self.output_filename = output_filename
        self.base_stations = base_stations
        self.clients = clients
        self.xlim = xlim
        self.map_limits = map_limits
        self.output_dpi = output_dpi
        self.scatter_size = scatter_size
        
        # Setup the figure for animation
        plt.ion()  # Enable interactive mode
        self.fig = plt.figure(figsize=(18, 10))  # Larger figure without constrained layout
        self.fig.canvas.manager.set_window_title('5G Network Slicing Visualization')
        
        # Setup GridSpec for layout with proper spacing
        self.gs = gridspec.GridSpec(3, 3, width_ratios=[6, 3, 3], figure=self.fig,
                                    wspace=0.4, hspace=0.5)  # Increased spacing between subplots
        
        # Initialize plots
        self.setup_plots()
        
        # Initialize colors for different slices
        self.slice_colors = {
            'x_eMBB': '#FF6B6B',      # Red for enhanced Mobile Broadband
            'y_eMBB': '#4ECDC4',      # Teal for another eMBB
            'x_URLLC': '#45B7D1',     # Blue for Ultra-Reliable Low-Latency
            'y_URLLC': '#96CEB4',     # Green for another URLLC
            'x_mMTC': '#FFBE0B',      # Yellow for massive Machine Type Communication
            'y_mMTC': '#FF9F1C',      # Orange for another mMTC
            'x_voice': '#A8E6CF',     # Light green for voice
            'y_voice': '#DCEDC1',     # Light yellow for another voice
            'x_eMBB_p': '#FF78C4',    # Pink for premium eMBB
            'y_eMBB_p': '#E7B7C8'     # Light pink for another premium eMBB
        }
            
        # Store data for updates
        self.current_data = {
            'connected_ratio': [],
            'bandwidth_usage': [],
            'slice_ratio': [],
            'client_ratio': [],
            'coverage_ratio': [],
            'block_ratio': [],
            'handover_ratio': []
        }
        
        # Track previous allocation for comparison
        self.previous_allocation = {}
        self.current_allocation = {}
        
        # Animation settings
        self.animation_interval = 100  # 100ms for smooth animation
        self.anim = None

    def setup_plots(self):
        """Initialize all subplot axes with enhanced layout"""
        # Main network topology plot
        self.map_ax = plt.subplot(self.gs[:, 0])
        self.map_ax.set_aspect('equal')
        self.map_ax.set_title('Network Topology and Slice Distribution', pad=20)
        
        # Create other subplots with enhanced styling
        self.stat_axes = {
            'slice_allocation': plt.subplot(self.gs[0, 1:]),
            'bandwidth': plt.subplot(self.gs[1, 1]),
            'client_ratio': plt.subplot(self.gs[1, 2]),
            'performance': plt.subplot(self.gs[2, 1]),
            'allocation_table': plt.subplot(self.gs[2, 2])  # New table for allocation
        }
        
        # Setup axes properties
        self.setup_axes_properties()

    def setup_axes_properties(self):
        """Set up enhanced properties for all axes"""
        # Setup map axes
        xlims, ylims = self.map_limits
        self.map_ax.set_xlim(xlims)
        self.map_ax.set_ylim(ylims)
        self.map_ax.yaxis.set_major_formatter(FormatStrFormatter('%.0f m'))
        self.map_ax.xaxis.set_major_formatter(FormatStrFormatter('%.0f m'))
        self.map_ax.grid(True, alpha=0.2, linestyle='--')
        
        # Setup other axes with titles and styling
        titles = {
            'slice_allocation': 'Network Slice Allocation',
            'bandwidth': 'Bandwidth Utilization per Slice',
            'client_ratio': 'Client Distribution',
            'performance': 'Network Performance Metrics',
            'allocation_table': 'Slice Allocation Changes'
        }
        
        for name, ax in self.stat_axes.items():
            ax.set_title(titles[name], pad=10)
            if name not in ['performance', 'allocation_table']:
                ax.set_xlim(self.xlim)
            if name == 'allocation_table':
                ax.axis('off')  # Turn off axes for table
            else:
                ax.grid(True, alpha=0.2, linestyle='--')
            ax.tick_params(labelsize=8)

    def draw_map(self):
        """Draw enhanced network map with slice visualization"""
        self.map_ax.clear()
        self.map_ax.set_title('Network Topology and Slice Distribution', pad=20)
        
        # Setup map properties again after clearing - use exact limit values to prevent zooming
        xlims, ylims = self.map_limits
        self.map_ax.set_xlim(xlims[0], xlims[1])
        self.map_ax.set_ylim(ylims[0], ylims[1])
        self.map_ax.set_autoscale_on(False)  # Disable autoscaling to prevent zoom
        self.map_ax.grid(True, alpha=0.2, linestyle='--')
        
        # Create fake handles for legend - one for each base station and client type
        base_station_handle = plt.Line2D([], [], marker='^', color='black', markerfacecolor='white', 
                                         markersize=10, linestyle='None', label='Base Station')
        coverage_handle = plt.Line2D([], [], marker='o', color='gray', markerfacecolor='gray', 
                                     alpha=0.1, markersize=10, linestyle='None', label='Coverage Area')
        
        legend_handles = [base_station_handle, coverage_handle]
        legend_labels = ['Base Station', 'Coverage Area']
        
        # Draw base stations with enhanced visualization
        for bs in self.base_stations:
            # Draw coverage area with gradient effect
            circle = plt.Circle(
                bs.coverage.center,
                bs.coverage.radius,
                fill=True,
                alpha=0.1,
                facecolor='gray',  # Use facecolor instead of color
                edgecolor='gray'   # Add matching edgecolor 
            )
            self.map_ax.add_artist(circle)
            
            # Draw base station symbol
            self.map_ax.plot(
                bs.coverage.center[0],
                bs.coverage.center[1],
                marker='^',
                markersize=10,
                color='black',
                markerfacecolor='white'
            )
            
            # Draw slice allocation indicators
            self.draw_slice_indicators(bs)
        
        # Group clients by slice for better visualization
        clients_by_slice = {}
        
        # Ensure clients have base_station and get_slice method
        for c in self.clients:
            if hasattr(c, 'base_station') and c.base_station is not None and hasattr(c, 'get_slice'):
                slice_obj = c.get_slice()
                if slice_obj and hasattr(slice_obj, 'name'):
                    slice_name = slice_obj.name
                    if slice_name not in clients_by_slice:
                        clients_by_slice[slice_name] = []
                    clients_by_slice[slice_name].append(c)
        
        # Add slice-specific handles to legend before drawing clients
        for slice_name in clients_by_slice.keys():
            color = self.slice_colors.get(slice_name, 'gray')
            active_handle = plt.Line2D([], [], marker='o', color=color, markersize=8, 
                                      linestyle='None', label=f'{slice_name} (Active)')
            inactive_handle = plt.Line2D([], [], marker='o', color=color, markersize=5, 
                                        alpha=0.3, linestyle='None', label=f'{slice_name} (Inactive)')
            
            legend_handles.extend([active_handle, inactive_handle])
            legend_labels.extend([f'{slice_name} (Active)', f'{slice_name} (Inactive)'])
        
        # Now draw the clients
        for slice_name, clients in clients_by_slice.items():
            if not clients:  # Skip if no clients for this slice
                continue
                
            x_coords = [c.x for c in clients]
            y_coords = [c.y for c in clients]
            connected = [c.connected for c in clients if hasattr(c, 'connected')]
            slice_color = self.slice_colors.get(slice_name, 'gray')
            
            # Make sure we have valid connected flags
            if not connected:
                connected = [True] * len(clients)  # Default to all connected if attribute missing
            
            # Draw connected clients
            connected_indices = [i for i, c in enumerate(connected) if c]
            if connected_indices:
                self.map_ax.scatter(
                    [x_coords[i] for i in connected_indices],
                    [y_coords[i] for i in connected_indices],
                    color=slice_color,
                    s=self.scatter_size * 2,
                    alpha=1.0
                )
            
            # Draw disconnected clients
            disconnected_indices = [i for i, c in enumerate(connected) if not c]
            if disconnected_indices:
                self.map_ax.scatter(
                    [x_coords[i] for i in disconnected_indices],
                    [y_coords[i] for i in disconnected_indices],
                    color=slice_color,
                    s=self.scatter_size,
                    alpha=0.3
                )
        
        # Add legend with all handles
        if legend_handles:
            legend = self.map_ax.legend(
                handles=legend_handles,
                labels=legend_labels,
                loc='upper center',
                bbox_to_anchor=(0.5, -0.05),
                fontsize=8,
                title='Network Elements',
                title_fontsize=10,
                ncol=min(4, len(legend_handles))
            )
            legend.get_frame().set_alpha(0.8)
        
        # Set axis labels
        self.map_ax.set_xlabel('Distance (m)', fontsize=10)
        self.map_ax.set_ylabel('Distance (m)', fontsize=10)

    def draw_slice_indicators(self, bs):
        """Draw indicators showing slice allocation for each base station"""
        center_x, center_y = bs.coverage.center
        radius = bs.coverage.radius * 0.15  # Increased size for better visibility
        
        # Calculate total capacity and used capacity for each slice
        total_capacity = sum(s.capacity.capacity for s in bs.slices)
        
        for i, slice in enumerate(bs.slices):
            # Calculate position for the indicator
            angle = 2 * np.pi * (i / len(bs.slices))
            dx = radius * np.cos(angle)
            dy = radius * np.sin(angle)
            
            # Calculate usage ratio
            usage_ratio = 1 - (slice.capacity.level / slice.capacity.capacity)
            
            # Draw slice indicator with border - use facecolor and edgecolor separately
            indicator = plt.Circle(
                (center_x + dx, center_y + dy),
                radius * 0.25,  # Increased size
                facecolor=self.slice_colors.get(slice.name, 'gray'),
                edgecolor='black',  # Add border for better visibility
                linewidth=1,
                alpha=0.7 if usage_ratio > 0 else 0.3
            )
            self.map_ax.add_artist(indicator)
            
            # Add small text showing slice type
            if usage_ratio > 0:  # Only show label for active slices
                text_x = center_x + dx * 1.2
                text_y = center_y + dy * 1.2
                self.map_ax.text(
                    text_x, text_y,
                    slice.name.split('_')[1] if '_' in slice.name else slice.name,  # Handle both formats
                    fontsize=6,
                    ha='center',
                    va='center',
                    bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=0.5)
                )

    def update_stat_plots(self):
        """Update statistical plots with enhanced visualization"""
        # Clear all stat axes
        for name, ax in self.stat_axes.items():
            ax.clear()
            # Re-set axis properties to prevent auto-scaling
            if name not in ['performance', 'allocation_table']:
                ax.set_xlim(self.xlim[0], self.xlim[1])
                ax.set_autoscale_on(False)  # Disable autoscaling
            
            # Set appropriate titles
            titles = {
                'slice_allocation': 'Network Slice Allocation',
                'bandwidth': 'Bandwidth Utilization per Slice',
                'client_ratio': 'Client Distribution',
                'performance': 'Network Performance Metrics',
                'allocation_table': 'Slice Allocation Changes'
            }
            ax.set_title(titles.get(name, name), pad=10)
        
        # Update slice allocation plot
        ax = self.stat_axes['slice_allocation']
        self.plot_slice_allocation(ax)
        
        # Update bandwidth utilization plot
        ax = self.stat_axes['bandwidth']
        self.plot_bandwidth_utilization(ax)
        
        # Update client distribution plot
        ax = self.stat_axes['client_ratio']
        self.plot_client_distribution(ax)
        
        # Update performance metrics plot
        ax = self.stat_axes['performance']
        self.plot_performance_metrics(ax)
        
        # Update allocation table plot
        ax = self.stat_axes['allocation_table']
        self.plot_allocation_table(ax)

    def plot_slice_allocation(self, ax):
        """Plot enhanced slice allocation visualization with previous comparison"""
        # Get all unique slice names
        slice_names = list(set(s.name for bs in self.base_stations for s in bs.slices))
        if not slice_names:
            return
            
        y_pos = np.arange(len(slice_names))
        
        # Calculate current allocation metrics
        current_allocations = []
        for slice_name in slice_names:
            total_allocated = sum(
                s.capacity.capacity - s.capacity.level
                for bs in self.base_stations
                for s in bs.slices
                if s.name == slice_name
            )
            current_allocations.append(total_allocated)
        
        # Calculate previous allocation metrics (if available)
        previous_allocations = []
        if self.previous_allocation:
            for slice_name in slice_names:
                if slice_name in self.previous_allocation:
                    prev_data = self.previous_allocation[slice_name]
                    previous_allocations.append(prev_data['used'])
                else:
                    previous_allocations.append(0)
        
        # Draw bars
        bar_height = 0.4  # Reduce height to fit both bars
        
        # Draw current allocation
        current_bars = ax.barh(
            y_pos, 
            current_allocations, 
            bar_height,
            color=[self.slice_colors.get(name, 'gray') for name in slice_names],
            label='Current Allocation',
            alpha=0.9,
            zorder=10
        )
        
        # Draw previous allocation if available
        if previous_allocations:
            prev_bars = ax.barh(
                y_pos - bar_height, 
                previous_allocations, 
                bar_height,
                color=[self.slice_colors.get(name, 'gray') for name in slice_names],
                alpha=0.4,
                label='Previous Allocation',
                zorder=5
            )
        
        # Customize appearance
        ax.set_yticks(y_pos - bar_height/2 if previous_allocations else y_pos)
        ax.set_yticklabels(slice_names, fontsize=8)
        ax.set_xlabel('Allocated Bandwidth (bps)', fontsize=8)
        ax.set_title('Network Slice Allocation', pad=10)
        
        # Add legend if showing comparison
        if previous_allocations:
            ax.legend(fontsize=7, loc='upper right')
        
        # Add value labels for current allocation
        for i, v in enumerate(current_allocations):
            if v > 0:  # Only show labels for non-zero values
                ax.text(
                    v, 
                    y_pos[i], 
                    format_bps(v), 
                    fontsize=7, 
                    va='center',
                    ha='left',
                    color='black'
                )

    def plot_bandwidth_utilization(self, ax):
        """Plot enhanced bandwidth utilization over time"""
        if self.current_data['bandwidth_usage']:
            ax.plot(self.current_data['bandwidth_usage'], 
                   color='#2ecc71', 
                   linewidth=2,
                   label='Total Usage')
            ax.fill_between(range(len(self.current_data['bandwidth_usage'])),
                          self.current_data['bandwidth_usage'],
                          alpha=0.2,
                          color='#2ecc71')
        
        ax.set_ylabel('Bandwidth (bps)', fontsize=8)
        ax.set_xlabel('Time', fontsize=8)
        ax.yaxis.set_major_formatter(FuncFormatter(format_bps))
        ax.grid(True, alpha=0.2, linestyle='--')

    def plot_client_distribution(self, ax):
        """Plot enhanced client distribution visualization"""
        if self.current_data['client_ratio']:
            ax.plot(self.current_data['client_ratio'],
                   color='#3498db',
                   linewidth=2,
                   label='Connected Clients')
            ax.fill_between(range(len(self.current_data['client_ratio'])),
                          self.current_data['client_ratio'],
                          alpha=0.2,
                          color='#3498db')
        
        ax.set_ylabel('Client Ratio', fontsize=8)
        ax.set_xlabel('Time', fontsize=8)
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: '{:.0%}'.format(y)))
        ax.grid(True, alpha=0.2, linestyle='--')

    def plot_performance_metrics(self, ax):
        """Plot enhanced performance metrics"""
        metrics = ['Coverage', 'Block Rate', 'Handover Rate']
        
        # Default to zero values if data is empty
        coverage_value = 0
        block_value = 0
        handover_value = 0
        
        # Safely get values from current data, with fallbacks
        if self.current_data['coverage_ratio'] and len(self.current_data['coverage_ratio']) > 0:
            coverage_value = self.current_data['coverage_ratio'][-1]
        
        if self.current_data['block_ratio'] and len(self.current_data['block_ratio']) > 0:
            block_value = self.current_data['block_ratio'][-1]
            
        if self.current_data['handover_ratio'] and len(self.current_data['handover_ratio']) > 0:
            handover_value = self.current_data['handover_ratio'][-1]
        
        values = [coverage_value, block_value, handover_value]
        
        # Make sure values are valid numbers
        for i in range(len(values)):
            if values[i] is None or not isinstance(values[i], (int, float)) or np.isnan(values[i]):
                values[i] = 0.0
        
        colors = ['#2ecc71', '#e74c3c', '#f1c40f']
        y_pos = np.arange(len(metrics))
        
        # Draw horizontal bars
        bars = ax.barh(y_pos, values, color=colors)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(metrics, fontsize=8)
        ax.set_xlim(0, 1)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: '{:.0%}'.format(x)))
        
        # Add value labels - handle zero values
        for i, v in enumerate(values):
            text = '{:.1%}'.format(v) if v > 0 else '0.0%'
            ax.text(max(v, 0.05), i, text, fontsize=7, va='center')

    def plot_allocation_table(self, ax):
        """Plot a table showing slice allocation changes"""
        ax.clear()
        ax.axis('off')
        
        # Prepare table data
        if not self.current_allocation:
            # No data yet
            return
        
        # Headers for the table
        col_labels = ['Slice', 'Alloc. (Mbps)', 'Used (%)', 'Clients', 'Change']
        rows = []
        cell_colors = []
        
        # Add data for each slice
        for slice_name, data in self.current_allocation.items():
            # Calculate metrics
            total_mbps = data['capacity'] / 1e6  # Convert to Mbps
            utilization = (data['used'] / data['capacity']) * 100 if data['capacity'] > 0 else 0
            
            # Format the change indicator
            if slice_name in self.previous_allocation:
                usage_change = data.get('usage_change', 0)
                change_text = f"{usage_change:+.1f}%" if usage_change != 0 else "-"
                
                # Color based on change
                if usage_change > 5:
                    change_color = '#f39c12'  # Warning (orange)
                elif usage_change > 15:
                    change_color = '#e74c3c'  # Critical (red)
                elif usage_change < -5:
                    change_color = '#2ecc71'  # Good (green)
                else:
                    change_color = 'white'  # Neutral
            else:
                change_text = "NEW"
                change_color = '#3498db'  # Blue for new
            
            # Add row data
            row = [
                slice_name,
                f"{total_mbps:.1f}",
                f"{utilization:.1f}%",
                f"{data['clients']}",
                change_text
            ]
            rows.append(row)
            
            # Row colors (slice-specific color for first cell, white for others except change)
            row_colors = [
                self.slice_colors.get(slice_name, 'gray'),  # Slice name
                'white',  # Allocation
                'white',  # Usage
                'white',  # Clients
                change_color  # Change
            ]
            cell_colors.append(row_colors)
        
        # Create the table
        table = ax.table(
            cellText=rows,
            colLabels=col_labels,
            loc='center',
            cellLoc='center',
            cellColours=cell_colors
        )
        
        # Style the table
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1.2, 1.5)
        
        # Adjust colors for header
        for i, key in enumerate(col_labels):
            cell = table[0, i]
            cell.set_facecolor('#2c3e50')
            cell.set_text_props(color='white')
        
        ax.set_title('Slice Allocation Changes', pad=10)

    def update(self, frame, *stats):
        """Update function for animation with enhanced visualization"""
        # Update statistics data
        for i, (key, data) in enumerate(self.current_data.items()):
            if len(stats) > i and len(stats[i]) > 0:
                data.append(stats[i][-1])
                if len(data) > self.xlim[1] - self.xlim[0]:
                    data.pop(0)
        
        # Store previous allocation before updating
        self.update_slice_allocation_data()
        
        # Update all plots
        self.draw_map()
        self.update_stat_plots()
        
        # Apply tight layout for better spacing
        self.fig.tight_layout()
        
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        
        return self.fig.get_axes()

    def update_slice_allocation_data(self):
        """Update the slice allocation data for comparison"""
        # Store previous allocation
        self.previous_allocation = self.current_allocation.copy() if self.current_allocation else {}
        
        # Get current allocation
        self.current_allocation = {}
        
        # Calculate allocation for each slice
        for bs in self.base_stations:
            for slice in bs.slices:
                slice_name = slice.name
                if slice_name not in self.current_allocation:
                    self.current_allocation[slice_name] = {
                        'capacity': 0,
                        'used': 0,
                        'clients': 0,
                        'qos_violations': 0
                    }
                
                # Add capacity and usage
                usage = slice.capacity.capacity - slice.capacity.level
                self.current_allocation[slice_name]['capacity'] += slice.capacity.capacity
                self.current_allocation[slice_name]['used'] += usage
                self.current_allocation[slice_name]['clients'] += slice.connected_users
                
        # Calculate change percentages if previous data exists
        if self.previous_allocation:
            for slice_name, data in self.current_allocation.items():
                if slice_name in self.previous_allocation:
                    prev = self.previous_allocation[slice_name]
                    # Calculate percentage changes
                    data['usage_change'] = ((data['used'] / data['capacity']) - 
                                           (prev['used'] / prev['capacity'])) * 100 if prev['capacity'] > 0 else 0
                    data['client_change'] = data['clients'] - prev['clients']
                else:
                    # New slice
                    data['usage_change'] = 100
                    data['client_change'] = data['clients']

    def draw_live(self, *stats):
        """Start real-time animation with enhanced visualization"""
        self.anim = animation.FuncAnimation(
            self.fig, 
            self.update, 
            fargs=stats,
            interval=self.animation_interval,
            blit=False,
            cache_frame_data=False,  # Disable frame caching to fix warning
            save_count=100  # Limit number of frames saved
        )
        plt.show(block=False)

    def save_fig(self):
        """Save the current figure with high quality"""
        self.fig.savefig(
            self.output_filename,
            dpi=self.output_dpi,
            bbox_inches='tight',
            pad_inches=0.1
        )

    def show_plot(self):
        plt.show()

    def get_map_limits(self):
        # deprecated
        x_min = min([bs.coverage.center[0]-bs.coverage.radius for bs in self.base_stations])
        x_max = max([bs.coverage.center[0]+bs.coverage.radius for bs in self.base_stations])
        y_min = min([bs.coverage.center[1]-bs.coverage.radius for bs in self.base_stations])
        y_max = max([bs.coverage.center[1]+bs.coverage.radius for bs in self.base_stations])

        return (x_min, x_max), (y_min, y_max)

    def draw_background_elements(self):
        """Draw background elements to make visualization more realistic"""
        # Add city blocks or buildings as rectangles
        buildings = [
            # Format: [x, y, width, height]
            [-200, -300, 150, 200],
            [300, 200, 250, 150],
            [-500, 200, 180, 220],
            [100, -400, 300, 120],
            [600, -150, 180, 300],
            [-300, 600, 220, 180],
        ]
        
        for x, y, w, h in buildings:
            rect = plt.Rectangle((x, y), w, h, facecolor='#95a5a6', alpha=0.3, edgecolor='#7f8c8d')
            self.map_ax.add_patch(rect)
        
        # Add roads as lines
        roads = [
            # Format: [x1, y1, x2, y2]
            [-800, 0, 800, 0],
            [0, -800, 0, 800],
            [-500, -500, 500, 500],
            [-500, 500, 500, -500],
            [-800, 600, 800, 600],
            [600, -800, 600, 800]
        ]
        
        for x1, y1, x2, y2 in roads:
            self.map_ax.plot([x1, x2], [y1, y2], color='#34495e', linestyle='-', linewidth=2, alpha=0.3)
        
        # Add points of interest (landmarks)
        landmarks = [
            # Format: [x, y, marker, name]
            [400, 400, 'P', 'Hospital'],
            [-400, -400, 's', 'Mall'],
            [700, -300, 'X', 'Stadium'],
            [-600, 300, '*', 'Park'],
            [0, 0, 'o', 'Downtown'],
        ]
        
        for x, y, marker, name in landmarks:
            self.map_ax.plot(x, y, marker=marker, markersize=10, color='#e74c3c')
            self.map_ax.text(x, y-40, name, fontsize=8, ha='center', bbox=dict(facecolor='white', alpha=0.7))

    def get_slice_description(self, slice_name):
        """Return a more descriptive name for a slice based on its type"""
        if '_eMBB' in slice_name:
            return 'High-bandwidth Video' if 'p' in slice_name else 'Broadband Users'
        elif '_URLLC' in slice_name:
            return 'Autonomous Vehicles'
        elif '_mMTC' in slice_name:
            return 'IoT Sensors'
        elif '_voice' in slice_name:
            return 'Voice Calls'
        else:
            return slice_name
