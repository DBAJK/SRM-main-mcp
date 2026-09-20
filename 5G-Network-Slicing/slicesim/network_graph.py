import matplotlib.pyplot as plt
import numpy as np
import networkx as nx
import random
import matplotlib.animation as animation
from matplotlib.patches import Patch, Circle
from matplotlib.collections import LineCollection

class NetworkGraphVisualization:
    def __init__(self, base_stations, clients):
        self.base_stations = base_stations
        self.clients = clients
        self.slice_colors = {
            'x_eMBB': '#FF6B6B',      # Red
            'y_eMBB': '#4ECDC4',      # Teal
            'x_URLLC': '#45B7D1',     # Blue
            'y_URLLC': '#96CEB4',     # Green
            'x_mMTC': '#FFBE0B',      # Yellow
            'y_mMTC': '#FF9F1C',      # Orange
            'x_voice': '#A8E6CF',     # Light green
            'y_voice': '#DCEDC1',     # Light yellow
            'x_eMBB_p': '#FF78C4',    # Pink
            'y_eMBB_p': '#E7B7C8'     # Light pink
        }
        
        # Create figure
        plt.ion()  # Enable interactive mode
        self.fig, self.ax = plt.subplots(figsize=(12, 10))
        self.fig.canvas.manager.set_window_title('5G Network Slice Performance')
        
        # Create a graph
        self.G = nx.Graph()
        
        # Store animated elements
        self.edge_lines = {}
        self.node_circles = {}
        self.util_markers = {}
        self.client_dots = {}
        
        # Animation
        self.anim = None
        self.frame_count = 0
        self.flow_points = {}  # Store points for animated flow
        self.animation_speed = 0.2  # Faster animation for more visible changes
        
        # For client dots animation
        self.client_assignment = {}  # Map clients to base stations
        
    def create_network_graph(self):
        # Clear previous graph and axes
        self.G.clear()
        self.ax.clear()
        self.edge_lines = {}
        self.node_circles = {}
        self.util_markers = {}
        self.client_dots = {}
        self.flow_points = {}
        
        # Add nodes for base stations
        for i, bs in enumerate(self.base_stations):
            # Add small random variations to utilization for more dynamic visualization
            utilization = [max(0.1, min(0.9, 1-(s.capacity.level/s.capacity.capacity) + random.uniform(-0.1, 0.2))) 
                           for s in bs.slices.values()]
            
            # Make sure the position is a tuple with two elements
            bs_pos = bs.coverage.center
            if not isinstance(bs_pos, tuple) or len(bs_pos) != 2:
                print(f"Warning: Invalid position for BS_{i}: {bs_pos}, using default")
                bs_pos = (i * 200, i * 200)  # Use a default position
            
            # Add node with position based on coverage center
            self.G.add_node(i, 
                           pos=bs_pos, 
                           type='base_station',
                           slices=[s.name for s in bs.slices.values()],
                           utilization=utilization)
        
        # Add connections between base stations if they're within range
        for i, bs1 in enumerate(self.base_stations):
            for j, bs2 in enumerate(self.base_stations):
                if i < j:  # Avoid duplicate edges
                    # Calculate distance between base stations
                    center1 = bs1.coverage.center
                    center2 = bs2.coverage.center
                    
                    # Make sure centers are properly formatted
                    if (not isinstance(center1, tuple) or len(center1) != 2 or 
                        not isinstance(center2, tuple) or len(center2) != 2):
                        continue  # Skip this edge if centers are invalid
                        
                    distance = np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
                    
                    # Check if their coverage areas overlap or are close
                    if distance < (bs1.coverage.radius + bs2.coverage.radius) * 1.5:
                        # Find common slices
                        bs1_slices = set(s.name for s in bs1.slices.values())
                        bs2_slices = set(s.name for s in bs2.slices.values())
                        common_slices = bs1_slices.intersection(bs2_slices)
                        
                        # Add edge with common slices as attribute
                        if common_slices:
                            self.G.add_edge(i, j, 
                                          common_slices=list(common_slices),
                                          weight=len(common_slices))
        
        # Get node positions from graph
        pos = nx.get_node_attributes(self.G, 'pos')
        
        # Draw connections first (background)
        for i, j in self.G.edges():
            edge_data = self.G.get_edge_data(i, j)
            common_slices = edge_data.get('common_slices', [])
            edge_key = (i, j)
            self.edge_lines[edge_key] = []
            
            # Create flow points for animation
            self.flow_points[edge_key] = {}
            
            # Get positions safely - handle any type errors
            if i not in pos or j not in pos:
                continue  # Skip this edge if positions are missing
                
            try:
                x1, y1 = pos[i]
                x2, y2 = pos[j]
            except (TypeError, ValueError):
                # If we can't unpack properly, skip this edge
                print(f"Warning: Invalid position format for edge {i}-{j}")
                continue
                
            edge_length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
            
            # Spread different slice connections slightly for better visibility
            offset = 0
            for slice_name in common_slices:
                # Get indices of this slice in each base station
                bs1_slices = [s.name for s in self.base_stations[i].slices]
                bs2_slices = [s.name for s in self.base_stations[j].slices]
                
                # Only draw if both have this slice
                if slice_name in bs1_slices and slice_name in bs2_slices:
                    # Get indices
                    idx1 = bs1_slices.index(slice_name)
                    idx2 = bs2_slices.index(slice_name)
                    
                    # Get utilization for this slice
                    util1 = self.G.nodes[i]['utilization'][idx1]
                    util2 = self.G.nodes[j]['utilization'][idx2]
                    
                    # Average utilization determines line width
                    avg_util = (util1 + util2) / 2
                    
                    # Calculate small offset to separate multiple slice lines
                    dx = (y2 - y1) / edge_length * offset * 5
                    dy = -(x2 - x1) / edge_length * offset * 5
                    
                    # Draw the edge
                    color = self.slice_colors.get(slice_name, 'gray')
                    line = self.ax.plot(
                        [x1 + dx, x2 + dx], 
                        [y1 + dy, y2 + dy], 
                        color=color,
                        linewidth=1 + 5 * avg_util,
                        alpha=0.5,
                        zorder=1,
                        label=slice_name
                    )[0]
                    
                    self.edge_lines[edge_key].append({
                        'line': line,
                        'color': color,
                        'slice': slice_name,
                        'util': avg_util,
                        'x_offset': dx,
                        'y_offset': dy
                    })
                    
                    # Add flow animation points
                    num_points = max(3, int(edge_length / 50))  # Number of animation points based on length
                    flow_particles = []
                    
                    for p in range(num_points):
                        # Random position along the line
                        point_pos = random.random()
                        # Create a scatter point for the animation
                        fp = self.ax.scatter(
                            x1 + dx + (x2 - x1 + 2*dx) * point_pos,
                            y1 + dy + (y2 - y1 + 2*dy) * point_pos,
                            s=20 + 30 * avg_util,
                            color=color,
                            alpha=0.8,
                            zorder=2
                        )
                        flow_particles.append({
                            'point': fp,
                            'pos': point_pos,
                            'speed': 0.01 + 0.05 * avg_util,  # Speed proportional to utilization
                            'x1': x1 + dx,
                            'y1': y1 + dy,
                            'x2': x2 + dx,
                            'y2': y2 + dy
                        })
                    
                    self.flow_points[edge_key][slice_name] = flow_particles
                    offset += 1
        
        # Draw base stations
        for i in self.G.nodes():
            # Skip nodes without position
            if i not in pos:
                continue
                
            try:
                node_data = self.G.nodes[i]
                x, y = pos[i]
            except (TypeError, ValueError):
                print(f"Warning: Invalid position format for node {i}")
                continue
                
            # Draw coverage area
            try:
                coverage = plt.Circle(
                    (x, y), 
                    self.base_stations[i].coverage.radius * 0.8,
                    facecolor='lightgray',
                    edgecolor='gray',
                    alpha=0.15,
                    zorder=0
                )
                self.ax.add_artist(coverage)
            except (AttributeError, ValueError, TypeError):
                print(f"Warning: Could not draw coverage for BS_{i}")
            
            # Draw circle for base station
            circle = plt.Circle(
                (x, y), 
                30, 
                facecolor='white', 
                edgecolor='black', 
                zorder=10
            )
            self.ax.add_artist(circle)
            self.node_circles[i] = circle
            
            # Draw node label
            self.ax.text(
                x, y, 
                str(i), 
                fontsize=12, 
                ha='center', 
                va='center', 
                weight='bold',
                zorder=15
            )
            
            # Draw slice utilization indicators around the node
            slices = node_data.get('slices', [])
            utilization = node_data.get('utilization', [])
            
            self.util_markers[i] = self.draw_utilization_indicators(x, y, slices, utilization)
        
        # Draw clients connecting to base stations
        self.draw_clients()
        
        # Create legend for slice types
        legend_elements = []
        for slice_name, color in self.slice_colors.items():
            if any(slice_name in self.G.nodes[i].get('slices', []) for i in self.G.nodes()):
                legend_elements.append(
                    Patch(facecolor=color, 
                         label=self.get_slice_description(slice_name))
                )
        
        # Add legend
        if legend_elements:
            self.ax.legend(
                handles=legend_elements, 
                loc='upper center', 
                bbox_to_anchor=(0.5, -0.05),
                ncol=min(3, len(legend_elements)),
                title="Slice Types"
            )
        
        # Set axis limits with some padding
        all_x = []
        all_y = []
        for node_id, position in pos.items():
            try:
                node_x, node_y = position
                all_x.append(node_x)
                all_y.append(node_y)
            except (TypeError, ValueError):
                continue
        
        if all_x and all_y:  # Check if lists are not empty
            padding = 300  # Padding in coordinate units
            self.ax.set_xlim(min(all_x) - padding, max(all_x) + padding)
            self.ax.set_ylim(min(all_y) - padding, max(all_y) + padding)
        else:
            # Set default limits if we couldn't find any valid positions
            self.ax.set_xlim(-1000, 1000)
            self.ax.set_ylim(-1000, 1000)
        
        # Equal aspect ratio
        self.ax.set_aspect('equal')
        
        # Set title and labels
        self.ax.set_title('Network Slice Connectivity and Utilization', fontsize=14)
        self.ax.set_xlabel('Distance (m)')
        self.ax.set_ylabel('Distance (m)')
        
        # Turn on grid
        self.ax.grid(True, linestyle='--', alpha=0.3)
        
        # Refresh canvas
        self.fig.tight_layout()
        self.fig.canvas.draw()
    
    def draw_clients(self):
        """Draw client devices on the map"""
        # First, assign clients to their closest base station
        if not self.client_assignment:
            # Initial assignment
            for c in self.clients:
                if hasattr(c, 'base_station') and c.base_station is not None:
                    bs_idx = c.base_station.id
                    if bs_idx not in self.client_assignment:
                        self.client_assignment[bs_idx] = []
                    self.client_assignment[bs_idx].append(c)
        
        # Draw clients as small dots around their base stations
        self.client_dots.clear()
        for bs_idx, clients in self.client_assignment.items():
            if bs_idx >= len(self.base_stations):
                continue  # Skip if base station doesn't exist
                
            bs = self.base_stations[bs_idx]
            center_x, center_y = bs.coverage.center
            
            # Get connected clients and group by slice
            clients_by_slice = {}
            for c in clients:
                if hasattr(c, 'get_slice') and c.get_slice() is not None:
                    slice_name = c.get_slice().name
                    if slice_name not in clients_by_slice:
                        clients_by_slice[slice_name] = []
                    clients_by_slice[slice_name].append(c)
            
            # Draw clients for each slice type
            for slice_name, slice_clients in clients_by_slice.items():
                color = self.slice_colors.get(slice_name, 'gray')
                
                # For each client, calculate a position around the base station
                for i, c in enumerate(slice_clients):
                    # Use client's actual position if available
                    if hasattr(c, 'x') and hasattr(c, 'y'):
                        client_x, client_y = c.x, c.y
                    else:
                        # Otherwise distribute around the base station
                        angle = 2 * np.pi * (i / len(slice_clients))
                        distance = random.uniform(50, bs.coverage.radius * 0.7)
                        client_x = center_x + distance * np.cos(angle)
                        client_y = center_y + distance * np.sin(angle)
                    
                    # Add some movement for animation
                    client_x += random.uniform(-10, 10)
                    client_y += random.uniform(-10, 10)
                    
                    # Draw the client
                    connected = hasattr(c, 'connected') and c.connected
                    alpha = 0.9 if connected else 0.3
                    size = 15 if connected else 7
                    
                    dot = self.ax.scatter(
                        client_x, client_y,
                        color=color,
                        s=size,
                        alpha=alpha,
                        edgecolor='white',
                        linewidth=0.5,
                        zorder=5
                    )
                    
                    # Store the dot
                    client_id = getattr(c, 'id', i)
                    self.client_dots[client_id] = {
                        'dot': dot,
                        'x': client_x,
                        'y': client_y,
                        'connected': connected,
                        'slice': slice_name,
                        'bs': bs_idx
                    }
                    
                    # Draw connection line to base station if connected
                    if connected:
                        self.ax.plot(
                            [client_x, center_x],
                            [client_y, center_y],
                            color=color,
                            alpha=0.2,
                            linewidth=0.5,
                            zorder=1
                        )
    
    def draw_utilization_indicators(self, x, y, slices, utilization):
        """Draw slice utilization indicators around the base station"""
        radius = 50  # Distance from center of node
        markers = {}
        
        for i, (slice_name, util) in enumerate(zip(slices, utilization)):
            # Calculate position around the circle
            angle = 2 * np.pi * (i / max(1, len(slices)))
            indicator_x = x + radius * np.cos(angle)
            indicator_y = y + radius * np.sin(angle)
            
            # Draw slice indicator
            size = 15 + util * 30  # Size increases with utilization
            marker = self.ax.scatter(
                indicator_x, indicator_y, 
                s=size,
                color=self.slice_colors.get(slice_name, 'gray'),
                edgecolor='black',
                linewidth=1,
                alpha=0.8,
                zorder=5
            )
            
            markers[slice_name] = {
                'marker': marker,
                'x': indicator_x,
                'y': indicator_y,
                'util': util,
                'angle': angle
            }
            
            # If utilization is significant, add label with percentage
            if util > 0.1:
                util_text = f"{int(util * 100)}%"
                self.ax.text(
                    indicator_x, indicator_y + 10, 
                    util_text,
                    fontsize=8,
                    ha='center',
                    bbox=dict(facecolor='white', alpha=0.7, pad=1, boxstyle='round'),
                    zorder=6
                )
        
        return markers
    
    def update_animation(self, frame):
        """Update animation frame"""
        self.frame_count += 1
        
        try:
            # Update flow particles along edges with faster movement
            for edge_key, slices in self.flow_points.items():
                for slice_name, particles in slices.items():
                    for p in particles:
                        # Move the particle along the line (faster)
                        p['pos'] += p['speed'] * 2  # Double speed for more visible movement
                        
                        # Reset if it goes beyond the end
                        if p['pos'] > 1.0:
                            p['pos'] = 0.0
                        
                        # Update position
                        new_x = p['x1'] + (p['x2'] - p['x1']) * p['pos']
                        new_y = p['y1'] + (p['y2'] - p['y1']) * p['pos']
                        
                        # Update the scatter plot
                        p['point'].set_offsets([new_x, new_y])
            
            # Update utilization values more frequently and with more variation
            if self.frame_count % 2 == 0:  # Every 2 frames instead of 5
                # Update node utilization indicators
                for i in self.G.nodes():
                    if i >= len(self.base_stations):
                        continue  # Skip if base station index is out of range
                        
                    slices = self.G.nodes[i].get('slices', [])
                    utilization = []
                    
                    for idx, s in enumerate(self.base_stations[i].slices):
                        try:
                            # Add more randomness for more dramatic visualization
                            base_util = 1-(s.capacity.level/s.capacity.capacity)
                            random_variation = random.uniform(-0.2, 0.3)  # Bigger changes
                            util = max(0.1, min(0.9, base_util + random_variation))
                            utilization.append(util)
                            
                            # Update the marker
                            if idx < len(slices):
                                slice_name = slices[idx]
                                if i in self.util_markers and slice_name in self.util_markers[i]:
                                    marker_info = self.util_markers[i][slice_name]
                                    marker = marker_info['marker']
                                    new_size = 15 + util * 40  # Bigger size change
                                    marker.set_sizes([new_size])
                        except (AttributeError, ZeroDivisionError, IndexError) as e:
                            # Handle errors gracefully
                            utilization.append(0.1)  # Default value
                    
                    # Update stored utilization
                    if utilization:
                        self.G.nodes[i]['utilization'] = utilization
                
                # Update edge thickness based on utilization
                for edge_key, lines in self.edge_lines.items():
                    i, j = edge_key
                    
                    # Skip if nodes don't exist in the graph
                    if i not in self.G.nodes() or j not in self.G.nodes():
                        continue
                        
                    for line_info in lines:
                        slice_name = line_info['slice']
                        
                        try:
                            # Get indices of this slice in each base station
                            bs1_slices = [s.name for s in self.base_stations[i].slices]
                            bs2_slices = [s.name for s in self.base_stations[j].slices]
                            
                            if slice_name in bs1_slices and slice_name in bs2_slices:
                                idx1 = bs1_slices.index(slice_name)
                                idx2 = bs2_slices.index(slice_name)
                                
                                # Get new utilization
                                util1 = self.G.nodes[i]['utilization'][idx1] if idx1 < len(self.G.nodes[i]['utilization']) else 0.1
                                util2 = self.G.nodes[j]['utilization'][idx2] if idx2 < len(self.G.nodes[j]['utilization']) else 0.1
                                avg_util = (util1 + util2) / 2
                                
                                # Update line width with more dramatic changes
                                line_info['line'].set_linewidth(1 + 8 * avg_util)
                                
                                # Update flow points size and speed
                                if slice_name in self.flow_points[edge_key]:
                                    for p in self.flow_points[edge_key][slice_name]:
                                        p['point'].set_sizes([20 + 40 * avg_util])
                                        p['speed'] = 0.02 + 0.08 * avg_util  # Faster movement
                        except (IndexError, KeyError, AttributeError) as e:
                            # Handle errors gracefully, but keep going
                            pass
            
            # Animate client dots every few frames with more movement
            if self.frame_count % 2 == 0:  # Every 2 frames instead of 3
                for client_id, info in list(self.client_dots.items()):
                    try:
                        # Add larger random movement
                        dx = random.uniform(-8, 8)  # Bigger movement range
                        dy = random.uniform(-8, 8)
                        
                        # Toggle connection status more frequently
                        if random.random() < 0.1:  # 10% chance to change instead of 5%
                            info['connected'] = not info['connected']
                            alpha = 0.9 if info['connected'] else 0.3
                            size = 18 if info['connected'] else 6  # More noticeable size difference
                            info['dot'].set_alpha(alpha)
                            info['dot'].set_sizes([size])
                        
                        # Update position
                        new_x = info['x'] + dx
                        new_y = info['y'] + dy
                        info['dot'].set_offsets([new_x, new_y])
                        info['x'] = new_x
                        info['y'] = new_y
                    except Exception:
                        # If there's any issue with this client dot, skip it
                        continue
                        
        except Exception as e:
            # Catch any other errors to avoid animation crashes
            print(f"Error in animation update: {str(e)}")
        
        return []
    
    def get_slice_description(self, slice_name):
        """Return a more descriptive name for a slice based on its type"""
        if '_eMBB' in slice_name:
            return 'High-bandwidth' if 'p' in slice_name else 'Broadband'
        elif '_URLLC' in slice_name:
            return 'Low-latency'
        elif '_mMTC' in slice_name:
            return 'IoT Sensors' 
        elif '_voice' in slice_name:
            return 'Voice'
        else:
            return slice_name
    
    def show(self):
        """Display the visualization"""
        self.create_network_graph()
        
        # Set up the animation
        self.anim = animation.FuncAnimation(
            self.fig, 
            self.update_animation,
            frames=100,
            interval=50,  # 50ms per frame instead of 100ms for faster updates
            blit=False
        )
        
        plt.show(block=False)
    
    def update(self):
        """Update the visualization (for live updates)"""
        try:
            # The animation is already running continuously, 
            # so we just need to update client positions and node assignments
            
            # Reassign clients to base stations (in case they moved)
            self.client_assignment = {}
            for c in self.clients:
                if hasattr(c, 'base_station') and c.base_station is not None:
                    try:
                        bs_idx = c.base_station.id
                        if bs_idx not in self.client_assignment:
                            self.client_assignment[bs_idx] = []
                        self.client_assignment[bs_idx].append(c)
                    except AttributeError:
                        # Skip clients with invalid base station info
                        continue
            
            # Re-draw everything (for major updates)
            if self.frame_count % 20 == 0:  # Every 20 frames do a complete redraw
                self.create_network_graph()
                
                # Restart animation
                if self.anim:
                    try:
                        self.anim.event_source.stop()
                    except Exception:
                        # If stopping animation fails, just continue
                        pass
                
                self.anim = animation.FuncAnimation(
                    self.fig, 
                    self.update_animation,
                    frames=100,
                    interval=50,
                    blit=False
                )
        except Exception as e:
            # Handle any unexpected errors
            print(f"Error updating network graph: {str(e)}")
            
        return self.fig 

    def run(self):
        """Run the visualization"""
        # Start the animation
        self.ani = animation.FuncAnimation(
            self.fig, self.update, interval=50, blit=False
        )
        plt.tight_layout()
        plt.show()

    def run_with_data(self, data):
        """Run the visualization with pregenerated data"""
        # Store the data
        self.pregenerated_data = data
        self.current_step = 0
        self.total_steps = len(data)
        
        # Add status text for data playback
        self.status_text = self.fig.text(
            0.5, 0.01, f"Step: 0/{self.total_steps-1}", 
            ha='center', fontsize=10, 
            bbox=dict(facecolor='white', alpha=0.7)
        )
        
        # Define key press handler for data playback
        def on_key_press(event):
            if event.key == 'n':
                # Next step
                self.current_step = min(self.current_step + 1, self.total_steps - 1)
                self.update_from_data()
            elif event.key == 'p':
                # Previous step
                self.current_step = max(0, self.current_step - 1)
                self.update_from_data()
            elif event.key == 's':
                # Skip 10 steps
                self.current_step = min(self.current_step + 10, self.total_steps - 1)
                self.update_from_data()
            elif event.key == 'r':
                # Restart
                self.current_step = 0
                self.update_from_data()
            elif event.key == 'a':
                # Toggle auto-play
                if hasattr(self, 'animation') and self.animation is not None:
                    # Stop animation
                    self.animation.event_source.stop()
                    self.animation = None
                    self.status_text.set_text(f"Step: {self.current_step}/{self.total_steps-1} (Paused)")
                else:
                    # Start animation
                    self.animation = animation.FuncAnimation(
                        self.fig, self.auto_advance_data, interval=200, blit=False
                    )
                    self.status_text.set_text(f"Step: {self.current_step}/{self.total_steps-1} (Playing)")
            
            plt.draw()
        
        # Connect key press event
        self.fig.canvas.mpl_connect('key_press_event', on_key_press)
        
        # Add instructions
        self.fig.text(
            0.5, 0.03, 
            "Press: 'n' next, 'p' previous, 's' skip 10, 'r' restart, 'a' toggle auto-play",
            ha='center', fontsize=10, 
            bbox=dict(facecolor='lightgray', alpha=0.5)
        )
        
        # Show initial state
        self.update_from_data()
        
        # Show the plot
        plt.tight_layout(rect=[0, 0.05, 1, 0.98])
        plt.show()
    
    def auto_advance_data(self, frame):
        """Auto-advance through data frames"""
        self.current_step = (self.current_step + 1) % self.total_steps
        self.update_from_data()
        return []
    
    def update_from_data(self):
        """Update visualization from data at current step"""
        # Get current state
        state = self.pregenerated_data[self.current_step]
        
        # Update status text
        self.status_text.set_text(f"Step: {self.current_step}/{self.total_steps-1} | Time: {state['timestamp']}")
        
        # Clear current graph
        self.ax.clear()
        self.setup_plot()
        
        # Recreate graph from state
        # 1. Update base stations
        self.nodes = {}
        for bs in state['base_stations']:
            node_id = f"BS{bs['id']}"
            
            # Create node
            pos = (bs['x'], bs['y'])
            
            # Calculate node size based on total allocation
            total_alloc = sum(bs['slice_allocation'].values())
            size = 300 + 300 * total_alloc  # Base size + allocation scaling
            
            # Draw coverage area
            coverage = plt.Circle(
                pos, bs['radius'], 
                alpha=0.1, fill=True, 
                edgecolor='gray', facecolor='lightgray'
            )
            self.ax.add_artist(coverage)
            
            # Draw node
            node = plt.Circle(
                pos, np.sqrt(size/np.pi), 
                alpha=0.8, fill=True, 
                edgecolor='black', facecolor='lightblue'
            )
            self.ax.add_artist(node)
            
            # Add to nodes dict
            self.nodes[node_id] = {
                'pos': pos,
                'size': size,
                'utilization': bs['slice_usage'],
                'slices': bs['slice_allocation'],
                'obj': node
            }
            
            # Add label
            self.ax.text(
                pos[0], pos[1], node_id,
                ha='center', va='center', fontsize=8,
                color='black', fontweight='bold'
            )
            
            # Draw slice indicators around base station
            self.draw_slice_indicators(pos, bs['slice_allocation'], bs['slice_usage'])
        
        # 2. Update clients
        self.client_nodes = {}
        for client in state['clients']:
            if not client['active']:
                continue
                
            client_id = f"C{client['id']}"
            pos = (client['x'], client['y'])
            bs_id = f"BS{client['base_station']}"
            slice_type = client['slice']
            
            # Get color for slice
            color = self.slice_colors.get(slice_type, 'gray')
            
            # Draw client node
            client_node = plt.Circle(
                pos, 5, 
                alpha=0.8, fill=True, 
                edgecolor='black', facecolor=color
            )
            self.ax.add_artist(client_node)
            
            # Add to client nodes dict
            self.client_nodes[client_id] = {
                'pos': pos,
                'base_station': bs_id,
                'slice': slice_type,
                'obj': client_node
            }
            
            # Draw connection to base station
            if bs_id in self.nodes:
                bs_pos = self.nodes[bs_id]['pos']
                self.ax.plot(
                    [pos[0], bs_pos[0]], [pos[1], bs_pos[1]],
                    color=color, alpha=0.3, linewidth=1
                )
        
        # 3. Add legend
        for slice_type, color in self.slice_colors.items():
            self.ax.plot([], [], 'o', color=color, label=slice_type)
        self.ax.legend(loc='upper right')
        
        # Refresh
        self.fig.canvas.draw_idle()
        
    def draw_slice_indicators(self, pos, slice_allocation, slice_usage):
        """Draw slice allocation indicators around a position"""
        x, y = pos
        radius = 40
        
        for i, (slice_type, allocation) in enumerate(slice_allocation.items()):
            if allocation <= 0:
                continue
                
            angle = 2 * np.pi * (i / len(slice_allocation))
            indicator_x = x + radius * np.cos(angle)
            indicator_y = y + radius * np.sin(angle)
            
            # Get color for slice
            color = self.slice_colors.get(slice_type, 'gray')
            
            # Draw slice allocation indicator (outer circle)
            size = 100 + 200 * allocation  # Size based on allocation
            
            outer = plt.Circle(
                (indicator_x, indicator_y), np.sqrt(size/np.pi),
                fill=True, alpha=0.4, facecolor=color, edgecolor='black'
            )
            self.ax.add_artist(outer)
            
            # Draw current usage (inner circle)
            usage = slice_usage.get(slice_type, 0)
            usage_size = size * (usage / max(0.01, allocation))
            
            inner = plt.Circle(
                (indicator_x, indicator_y), np.sqrt(usage_size/np.pi),
                fill=True, alpha=0.8, facecolor=color
            )
            self.ax.add_artist(inner)
            
            # Add label
            label_x = indicator_x + 5
            label_y = indicator_y + 5
            self.ax.text(
                label_x, label_y, slice_type,
                fontsize=8, ha='left', va='bottom'
            )
        
    def setup_plot(self):
        # Clear previous graph and axes
        self.G.clear()
        self.ax.clear()
        self.edge_lines = {}
        self.node_circles = {}
        self.util_markers = {}
        self.client_dots = {}
        self.flow_points = {}
        
        # Add nodes for base stations
        for i, bs in enumerate(self.base_stations):
            # Add small random variations to utilization for more dynamic visualization
            utilization = [max(0.1, min(0.9, 1-(s.capacity.level/s.capacity.capacity) + random.uniform(-0.1, 0.2))) 
                           for s in bs.slices.values()]
            
            # Make sure the position is a tuple with two elements
            bs_pos = bs.coverage.center
            if not isinstance(bs_pos, tuple) or len(bs_pos) != 2:
                print(f"Warning: Invalid position for BS_{i}: {bs_pos}, using default")
                bs_pos = (i * 200, i * 200)  # Use a default position
            
            # Add node with position based on coverage center
            self.G.add_node(i, 
                           pos=bs_pos, 
                           type='base_station',
                           slices=[s.name for s in bs.slices.values()],
                           utilization=utilization)
        
        # Add connections between base stations if they're within range
        for i, bs1 in enumerate(self.base_stations):
            for j, bs2 in enumerate(self.base_stations):
                if i < j:  # Avoid duplicate edges
                    # Calculate distance between base stations
                    center1 = bs1.coverage.center
                    center2 = bs2.coverage.center
                    
                    # Make sure centers are properly formatted
                    if (not isinstance(center1, tuple) or len(center1) != 2 or 
                        not isinstance(center2, tuple) or len(center2) != 2):
                        continue  # Skip this edge if centers are invalid
                        
                    distance = np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
                    
                    # Check if their coverage areas overlap or are close
                    if distance < (bs1.coverage.radius + bs2.coverage.radius) * 1.5:
                        # Find common slices
                        bs1_slices = set(s.name for s in bs1.slices.values())
                        bs2_slices = set(s.name for s in bs2.slices.values())
                        common_slices = bs1_slices.intersection(bs2_slices)
                        
                        # Add edge with common slices as attribute
                        if common_slices:
                            self.G.add_edge(i, j, 
                                          common_slices=list(common_slices),
                                          weight=len(common_slices))
        
        # Get node positions from graph
        pos = nx.get_node_attributes(self.G, 'pos')
        
        # Draw connections first (background)
        for i, j in self.G.edges():
            edge_data = self.G.get_edge_data(i, j)
            common_slices = edge_data.get('common_slices', [])
            edge_key = (i, j)
            self.edge_lines[edge_key] = []
            
            # Create flow points for animation
            self.flow_points[edge_key] = {}
            
            # Get positions safely - handle any type errors
            if i not in pos or j not in pos:
                continue  # Skip this edge if positions are missing
                
            try:
                x1, y1 = pos[i]
                x2, y2 = pos[j]
            except (TypeError, ValueError):
                # If we can't unpack properly, skip this edge
                print(f"Warning: Invalid position format for edge {i}-{j}")
                continue
                
            edge_length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
            
            # Spread different slice connections slightly for better visibility
            offset = 0
            for slice_name in common_slices:
                # Get indices of this slice in each base station
                bs1_slices = [s.name for s in self.base_stations[i].slices]
                bs2_slices = [s.name for s in self.base_stations[j].slices]
                
                # Only draw if both have this slice
                if slice_name in bs1_slices and slice_name in bs2_slices:
                    # Get indices
                    idx1 = bs1_slices.index(slice_name)
                    idx2 = bs2_slices.index(slice_name)
                    
                    # Get utilization for this slice
                    util1 = self.G.nodes[i]['utilization'][idx1]
                    util2 = self.G.nodes[j]['utilization'][idx2]
                    
                    # Average utilization determines line width
                    avg_util = (util1 + util2) / 2
                    
                    # Calculate small offset to separate multiple slice lines
                    dx = (y2 - y1) / edge_length * offset * 5
                    dy = -(x2 - x1) / edge_length * offset * 5
                    
                    # Draw the edge
                    color = self.slice_colors.get(slice_name, 'gray')
                    line = self.ax.plot(
                        [x1 + dx, x2 + dx], 
                        [y1 + dy, y2 + dy], 
                        color=color,
                        linewidth=1 + 5 * avg_util,
                        alpha=0.5,
                        zorder=1,
                        label=slice_name
                    )[0]
                    
                    self.edge_lines[edge_key].append({
                        'line': line,
                        'color': color,
                        'slice': slice_name,
                        'util': avg_util,
                        'x_offset': dx,
                        'y_offset': dy
                    })
                    
                    # Add flow animation points
                    num_points = max(3, int(edge_length / 50))  # Number of animation points based on length
                    flow_particles = []
                    
                    for p in range(num_points):
                        # Random position along the line
                        point_pos = random.random()
                        # Create a scatter point for the animation
                        fp = self.ax.scatter(
                            x1 + dx + (x2 - x1 + 2*dx) * point_pos,
                            y1 + dy + (y2 - y1 + 2*dy) * point_pos,
                            s=20 + 30 * avg_util,
                            color=color,
                            alpha=0.8,
                            zorder=2
                        )
                        flow_particles.append({
                            'point': fp,
                            'pos': point_pos,
                            'speed': 0.01 + 0.05 * avg_util,  # Speed proportional to utilization
                            'x1': x1 + dx,
                            'y1': y1 + dy,
                            'x2': x2 + dx,
                            'y2': y2 + dy
                        })
                    
                    self.flow_points[edge_key][slice_name] = flow_particles
                    offset += 1
        
        # Draw base stations
        for i in self.G.nodes():
            # Skip nodes without position
            if i not in pos:
                continue
                
            try:
                node_data = self.G.nodes[i]
                x, y = pos[i]
            except (TypeError, ValueError):
                print(f"Warning: Invalid position format for node {i}")
                continue
                
            # Draw coverage area
            try:
                coverage = plt.Circle(
                    (x, y), 
                    self.base_stations[i].coverage.radius * 0.8,
                    facecolor='lightgray',
                    edgecolor='gray',
                    alpha=0.15,
                    zorder=0
                )
                self.ax.add_artist(coverage)
            except (AttributeError, ValueError, TypeError):
                print(f"Warning: Could not draw coverage for BS_{i}")
            
            # Draw circle for base station
            circle = plt.Circle(
                (x, y), 
                30, 
                facecolor='white', 
                edgecolor='black', 
                zorder=10
            )
            self.ax.add_artist(circle)
            self.node_circles[i] = circle
            
            # Draw node label
            self.ax.text(
                x, y, 
                str(i), 
                fontsize=12, 
                ha='center', 
                va='center', 
                weight='bold',
                zorder=15
            )
            
            # Draw slice utilization indicators around the node
            slices = node_data.get('slices', [])
            utilization = node_data.get('utilization', [])
            
            self.util_markers[i] = self.draw_utilization_indicators(x, y, slices, utilization)
        
        # Draw clients connecting to base stations
        self.draw_clients()
        
        # Create legend for slice types
        legend_elements = []
        for slice_name, color in self.slice_colors.items():
            if any(slice_name in self.G.nodes[i].get('slices', []) for i in self.G.nodes()):
                legend_elements.append(
                    Patch(facecolor=color, 
                         label=self.get_slice_description(slice_name))
                )
        
        # Add legend
        if legend_elements:
            self.ax.legend(
                handles=legend_elements, 
                loc='upper center', 
                bbox_to_anchor=(0.5, -0.05),
                ncol=min(3, len(legend_elements)),
                title="Slice Types"
            )
        
        # Set axis limits with some padding
        all_x = []
        all_y = []
        for node_id, position in pos.items():
            try:
                node_x, node_y = position
                all_x.append(node_x)
                all_y.append(node_y)
            except (TypeError, ValueError):
                continue
        
        if all_x and all_y:  # Check if lists are not empty
            padding = 300  # Padding in coordinate units
            self.ax.set_xlim(min(all_x) - padding, max(all_x) + padding)
            self.ax.set_ylim(min(all_y) - padding, max(all_y) + padding)
        else:
            # Set default limits if we couldn't find any valid positions
            self.ax.set_xlim(-1000, 1000)
            self.ax.set_ylim(-1000, 1000)
        
        # Equal aspect ratio
        self.ax.set_aspect('equal')
        
        # Set title and labels
        self.ax.set_title('Network Slice Connectivity and Utilization', fontsize=14)
        self.ax.set_xlabel('Distance (m)')
        self.ax.set_ylabel('Distance (m)')
        
        # Turn on grid
        self.ax.grid(True, linestyle='--', alpha=0.3)
        
        # Refresh canvas
        self.fig.tight_layout()
        self.fig.canvas.draw()
        
    def draw_clients(self):
        """Draw client devices on the map"""
        # First, assign clients to their closest base station
        if not self.client_assignment:
            # Initial assignment
            for c in self.clients:
                if hasattr(c, 'base_station') and c.base_station is not None:
                    bs_idx = c.base_station.id
                    if bs_idx not in self.client_assignment:
                        self.client_assignment[bs_idx] = []
                    self.client_assignment[bs_idx].append(c)
        
        # Draw clients as small dots around their base stations
        self.client_dots.clear()
        for bs_idx, clients in self.client_assignment.items():
            if bs_idx >= len(self.base_stations):
                continue  # Skip if base station doesn't exist
                
            bs = self.base_stations[bs_idx]
            center_x, center_y = bs.coverage.center
            
            # Get connected clients and group by slice
            clients_by_slice = {}
            for c in clients:
                if hasattr(c, 'get_slice') and c.get_slice() is not None:
                    slice_name = c.get_slice().name
                    if slice_name not in clients_by_slice:
                        clients_by_slice[slice_name] = []
                    clients_by_slice[slice_name].append(c)
            
            # Draw clients for each slice type
            for slice_name, slice_clients in clients_by_slice.items():
                color = self.slice_colors.get(slice_name, 'gray')
                
                # For each client, calculate a position around the base station
                for i, c in enumerate(slice_clients):
                    # Use client's actual position if available
                    if hasattr(c, 'x') and hasattr(c, 'y'):
                        client_x, client_y = c.x, c.y
                    else:
                        # Otherwise distribute around the base station
                        angle = 2 * np.pi * (i / len(slice_clients))
                        distance = random.uniform(50, bs.coverage.radius * 0.7)
                        client_x = center_x + distance * np.cos(angle)
                        client_y = center_y + distance * np.sin(angle)
                    
                    # Add some movement for animation
                    client_x += random.uniform(-10, 10)
                    client_y += random.uniform(-10, 10)
                    
                    # Draw the client
                    connected = hasattr(c, 'connected') and c.connected
                    alpha = 0.9 if connected else 0.3
                    size = 15 if connected else 7
                    
                    dot = self.ax.scatter(
                        client_x, client_y,
                        color=color,
                        s=size,
                        alpha=alpha,
                        edgecolor='white',
                        linewidth=0.5,
                        zorder=5
                    )
                    
                    # Store the dot
                    client_id = getattr(c, 'id', i)
                    self.client_dots[client_id] = {
                        'dot': dot,
                        'x': client_x,
                        'y': client_y,
                        'connected': connected,
                        'slice': slice_name,
                        'bs': bs_idx
                    }
                    
                    # Draw connection line to base station if connected
                    if connected:
                        self.ax.plot(
                            [client_x, center_x],
                            [client_y, center_y],
                            color=color,
                            alpha=0.2,
                            linewidth=0.5,
                            zorder=1
                        )
    
    def draw_utilization_indicators(self, x, y, slices, utilization):
        """Draw slice utilization indicators around the base station"""
        radius = 50  # Distance from center of node
        markers = {}
        
        for i, (slice_name, util) in enumerate(zip(slices, utilization)):
            # Calculate position around the circle
            angle = 2 * np.pi * (i / max(1, len(slices)))
            indicator_x = x + radius * np.cos(angle)
            indicator_y = y + radius * np.sin(angle)
            
            # Draw slice indicator
            size = 15 + util * 30  # Size increases with utilization
            marker = self.ax.scatter(
                indicator_x, indicator_y, 
                s=size,
                color=self.slice_colors.get(slice_name, 'gray'),
                edgecolor='black',
                linewidth=1,
                alpha=0.8,
                zorder=5
            )
            
            markers[slice_name] = {
                'marker': marker,
                'x': indicator_x,
                'y': indicator_y,
                'util': util,
                'angle': angle
            }
            
            # If utilization is significant, add label with percentage
            if util > 0.1:
                util_text = f"{int(util * 100)}%"
                self.ax.text(
                    indicator_x, indicator_y + 10, 
                    util_text,
                    fontsize=8,
                    ha='center',
                    bbox=dict(facecolor='white', alpha=0.7, pad=1, boxstyle='round'),
                    zorder=6
                )
        
        return markers
    
    def update_animation(self, frame):
        """Update animation frame"""
        self.frame_count += 1
        
        try:
            # Update flow particles along edges with faster movement
            for edge_key, slices in self.flow_points.items():
                for slice_name, particles in slices.items():
                    for p in particles:
                        # Move the particle along the line (faster)
                        p['pos'] += p['speed'] * 2  # Double speed for more visible movement
                        
                        # Reset if it goes beyond the end
                        if p['pos'] > 1.0:
                            p['pos'] = 0.0
                        
                        # Update position
                        new_x = p['x1'] + (p['x2'] - p['x1']) * p['pos']
                        new_y = p['y1'] + (p['y2'] - p['y1']) * p['pos']
                        
                        # Update the scatter plot
                        p['point'].set_offsets([new_x, new_y])
            
            # Update utilization values more frequently and with more variation
            if self.frame_count % 2 == 0:  # Every 2 frames instead of 5
                # Update node utilization indicators
                for i in self.G.nodes():
                    if i >= len(self.base_stations):
                        continue  # Skip if base station index is out of range
                        
                    slices = self.G.nodes[i].get('slices', [])
                    utilization = []
                    
                    for idx, s in enumerate(self.base_stations[i].slices):
                        try:
                            # Add more randomness for more dramatic visualization
                            base_util = 1-(s.capacity.level/s.capacity.capacity)
                            random_variation = random.uniform(-0.2, 0.3)  # Bigger changes
                            util = max(0.1, min(0.9, base_util + random_variation))
                            utilization.append(util)
                            
                            # Update the marker
                            if idx < len(slices):
                                slice_name = slices[idx]
                                if i in self.util_markers and slice_name in self.util_markers[i]:
                                    marker_info = self.util_markers[i][slice_name]
                                    marker = marker_info['marker']
                                    new_size = 15 + util * 40  # Bigger size change
                                    marker.set_sizes([new_size])
                        except (AttributeError, ZeroDivisionError, IndexError) as e:
                            # Handle errors gracefully
                            utilization.append(0.1)  # Default value
                    
                    # Update stored utilization
                    if utilization:
                        self.G.nodes[i]['utilization'] = utilization
                
                # Update edge thickness based on utilization
                for edge_key, lines in self.edge_lines.items():
                    i, j = edge_key
                    
                    # Skip if nodes don't exist in the graph
                    if i not in self.G.nodes() or j not in self.G.nodes():
                        continue
                        
                    for line_info in lines:
                        slice_name = line_info['slice']
                        
                        try:
                            # Get indices of this slice in each base station
                            bs1_slices = [s.name for s in self.base_stations[i].slices]
                            bs2_slices = [s.name for s in self.base_stations[j].slices]
                            
                            if slice_name in bs1_slices and slice_name in bs2_slices:
                                idx1 = bs1_slices.index(slice_name)
                                idx2 = bs2_slices.index(slice_name)
                                
                                # Get new utilization
                                util1 = self.G.nodes[i]['utilization'][idx1] if idx1 < len(self.G.nodes[i]['utilization']) else 0.1
                                util2 = self.G.nodes[j]['utilization'][idx2] if idx2 < len(self.G.nodes[j]['utilization']) else 0.1
                                avg_util = (util1 + util2) / 2
                                
                                # Update line width with more dramatic changes
                                line_info['line'].set_linewidth(1 + 8 * avg_util)
                                
                                # Update flow points size and speed
                                if slice_name in self.flow_points[edge_key]:
                                    for p in self.flow_points[edge_key][slice_name]:
                                        p['point'].set_sizes([20 + 40 * avg_util])
                                        p['speed'] = 0.02 + 0.08 * avg_util  # Faster movement
                        except (IndexError, KeyError, AttributeError) as e:
                            # Handle errors gracefully, but keep going
                            pass
            
            # Animate client dots every few frames with more movement
            if self.frame_count % 2 == 0:  # Every 2 frames instead of 3
                for client_id, info in list(self.client_dots.items()):
                    try:
                        # Add larger random movement
                        dx = random.uniform(-8, 8)  # Bigger movement range
                        dy = random.uniform(-8, 8)
                        
                        # Toggle connection status more frequently
                        if random.random() < 0.1:  # 10% chance to change instead of 5%
                            info['connected'] = not info['connected']
                            alpha = 0.9 if info['connected'] else 0.3
                            size = 18 if info['connected'] else 6  # More noticeable size difference
                            info['dot'].set_alpha(alpha)
                            info['dot'].set_sizes([size])
                        
                        # Update position
                        new_x = info['x'] + dx
                        new_y = info['y'] + dy
                        info['dot'].set_offsets([new_x, new_y])
                        info['x'] = new_x
                        info['y'] = new_y
                    except Exception:
                        # If there's any issue with this client dot, skip it
                        continue
                        
        except Exception as e:
            # Catch any other errors to avoid animation crashes
            print(f"Error in animation update: {str(e)}")
        
        return []
    
    def get_slice_description(self, slice_name):
        """Return a more descriptive name for a slice based on its type"""
        if '_eMBB' in slice_name:
            return 'High-bandwidth' if 'p' in slice_name else 'Broadband'
        elif '_URLLC' in slice_name:
            return 'Low-latency'
        elif '_mMTC' in slice_name:
            return 'IoT Sensors' 
        elif '_voice' in slice_name:
            return 'Voice'
        else:
            return slice_name
    
    def show(self):
        """Display the visualization"""
        self.create_network_graph()
        
        # Set up the animation
        self.anim = animation.FuncAnimation(
            self.fig, 
            self.update_animation,
            frames=100,
            interval=50,  # 50ms per frame instead of 100ms for faster updates
            blit=False
        )
        
        plt.show(block=False)
    
    def update(self):
        """Update the visualization (for live updates)"""
        try:
            # The animation is already running continuously, 
            # so we just need to update client positions and node assignments
            
            # Reassign clients to base stations (in case they moved)
            self.client_assignment = {}
            for c in self.clients:
                if hasattr(c, 'base_station') and c.base_station is not None:
                    try:
                        bs_idx = c.base_station.id
                        if bs_idx not in self.client_assignment:
                            self.client_assignment[bs_idx] = []
                        self.client_assignment[bs_idx].append(c)
                    except AttributeError:
                        # Skip clients with invalid base station info
                        continue
            
            # Re-draw everything (for major updates)
            if self.frame_count % 20 == 0:  # Every 20 frames do a complete redraw
                self.create_network_graph()
                
                # Restart animation
                if self.anim:
                    try:
                        self.anim.event_source.stop()
                    except Exception:
                        # If stopping animation fails, just continue
                        pass
                
                self.anim = animation.FuncAnimation(
                    self.fig, 
                    self.update_animation,
                    frames=100,
                    interval=50,
                    blit=False
                )
        except Exception as e:
            # Handle any unexpected errors
            print(f"Error updating network graph: {str(e)}")
            
        return self.fig 
