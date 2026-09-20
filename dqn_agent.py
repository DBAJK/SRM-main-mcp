#!/usr/bin/env python3
"""
DQN Agent for 5G Network Slicing Orchestrator

This module implements a Deep Q-Network (DQN) agent for optimizing
slice resource allocation in 5G networks through reinforcement learning.
"""

import os
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense, BatchNormalization, Dropout
from tensorflow.keras.optimizers import Adam
from collections import deque
import random
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ReplayBuffer:
    """Experience replay buffer for DQN agent."""
    
    def __init__(self, buffer_size=10000):
        """Initialize replay buffer.
        
        Args:
            buffer_size (int): Maximum size of buffer
        """
        self.buffer = deque(maxlen=buffer_size)
    
    def store(self, state, action, reward, next_state, done):
        """Store experience in buffer.
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether episode is done
        """
        self.buffer.append((state, action, reward, next_state, done))
    
    def sample(self, batch_size):
        """Sample random batch from buffer.
        
        Args:
            batch_size (int): Size of batch to sample
            
        Returns:
            tuple: Batch of experiences (states, actions, rewards, next_states, dones)
        """
        batch = random.sample(self.buffer, min(len(self.buffer), batch_size))
        states, actions, rewards, next_states, dones = map(np.array, zip(*batch))
        return states, actions, rewards, next_states, dones
    
    def size(self):
        """Get current size of buffer.
        
        Returns:
            int: Current size of buffer
        """
        return len(self.buffer)


class DQNAgent:
    """DQN agent for network slice allocation."""
    
    def __init__(self, state_dim=14, action_dim=27, model_path=None):
        """Initialize DQN agent.
        
        Args:
            state_dim (int): Dimension of state space
            action_dim (int): Dimension of action space
            model_path (str): Path to load model from
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.model_path = model_path
        
        # Hyperparameters
        self.gamma = 0.95  # Discount factor
        self.epsilon = 1.0  # Exploration rate
        self.epsilon_decay = 0.995
        self.epsilon_min = 0.01
        self.learning_rate = 0.001
        self.batch_size = 64
        self.update_target_freq = 10  # Update target network every N steps
        
        # Create replay buffer
        self.replay_buffer = ReplayBuffer()
        
        # Step counter
        self.steps = 0
        
        # Initialize networks
        if model_path and os.path.exists(model_path):
            try:
                self.q_network = load_model(model_path)
                logger.info(f"Loaded DQN model from {model_path}")
                # Create target network with same weights
                self.target_network = keras.models.clone_model(self.q_network)
                self.target_network.set_weights(self.q_network.get_weights())
            except Exception as e:
                logger.error(f"Error loading model: {e}")
                self.q_network = self._build_model()
                self.target_network = keras.models.clone_model(self.q_network)
                self.target_network.set_weights(self.q_network.get_weights())
        else:
            self.q_network = self._build_model()
            self.target_network = keras.models.clone_model(self.q_network)
            self.target_network.set_weights(self.q_network.get_weights())
    
    def _build_model(self):
        """Build DQN model.
        
        Returns:
            keras.Model: DQN model
        """
        logger.info("Building DQN model")
        
        model = Sequential([
            # Input layer
            Dense(128, input_dim=self.state_dim, activation='relu'),
            BatchNormalization(),
            Dropout(0.3),
            
            # Hidden layers
            Dense(64, activation='relu'),
            BatchNormalization(),
            Dropout(0.3),
            
            Dense(32, activation='relu'),
            
            # Output layer (Q-values for each action)
            Dense(self.action_dim, activation='linear')
        ])
        
        # Compile model
        model.compile(
            optimizer=Adam(learning_rate=self.learning_rate),
            loss='mse'
        )
        
        # Print model summary
        model.summary()
        
        return model
    
    def get_action(self, state):
        """Get action based on current state.
        
        Args:
            state: Current state
            
        Returns:
            int: Selected action
        """
        # Epsilon-greedy action selection
        if np.random.rand() < self.epsilon:
            # Explore: select random action
            return np.random.randint(self.action_dim)
        else:
            # Exploit: select best action
            q_values = self.q_network.predict(np.array([state]), verbose=0)
            return np.argmax(q_values[0])
    
    def train_step(self):
        """Perform one training step.
        
        Returns:
            float: Loss value
        """
        # Check if enough experiences in buffer
        if self.replay_buffer.size() < self.batch_size:
            return None
        
        # Sample batch from replay buffer
        states, actions, rewards, next_states, dones = self.replay_buffer.sample(self.batch_size)
        
        # Get current Q values
        current_q = self.q_network.predict(states, verbose=0)
        
        # Get target Q values from target network
        target_q = np.copy(current_q)
        next_q = self.target_network.predict(next_states, verbose=0)
        
        # Update target Q values
        for i in range(self.batch_size):
            if dones[i]:
                target_q[i, actions[i]] = rewards[i]
            else:
                target_q[i, actions[i]] = rewards[i] + self.gamma * np.max(next_q[i])
        
        # Train model
        history = self.q_network.fit(states, target_q, epochs=1, verbose=0)
        loss = history.history['loss'][0]
        
        # Decay epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
        
        # Increment step counter
        self.steps += 1
        
        # Update target network if needed
        if self.steps % self.update_target_freq == 0:
            self.update_target_network()
            logger.info(f"Updated target network (step {self.steps})")
        
        return loss
    
    def update_target_network(self):
        """Update target network with weights from Q-network."""
        self.target_network.set_weights(self.q_network.get_weights())
    
    def store_transition(self, state, action, reward, next_state, done):
        """Store transition in replay buffer.
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether episode is done
        """
        self.replay_buffer.store(state, action, reward, next_state, done)
    
    def save_model(self, path=None):
        """Save model.
        
        Args:
            path (str): Path to save model
        """
        if path is None:
            path = self.model_path or "dqn_model"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        
        # Save model
        self.q_network.save(path)
        logger.info(f"DQN model saved to {path}")
    
    def load_model(self, path):
        """Load model.
        
        Args:
            path (str): Path to load model from
        """
        try:
            self.q_network = load_model(path)
            self.target_network = keras.models.clone_model(self.q_network)
            self.target_network.set_weights(self.q_network.get_weights())
            logger.info(f"DQN model loaded from {path}")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
    
    def calculate_reward(self, state, action, next_state):
        """Calculate reward for transition.
        
        Args:
            state: Current state dictionary
            action: Action taken
            next_state: Next state dictionary
            
        Returns:
            float: Reward
        """
        reward = 0
        
        # Extract relevant information from state dictionaries
        current_allocation = state['allocation']
        next_allocation = next_state['allocation']
        next_utilization = next_state['utilization']
        violations = next_state['violations']
        
        # Base reward for keeping utilization in optimal range (0.7-0.9)
        for i, util in enumerate(next_utilization):
            if 0.7 <= util <= 0.9:
                reward += 2.0
            elif util > 1.0:  # QoS violation
                reward -= 5.0 * (util - 1.0)
            elif util < 0.5:  # Underutilization
                reward -= 1.0 * (0.5 - util)
        
        # Penalty for allocation changes (encourage stability)
        allocation_change = np.sum(np.abs(next_allocation - current_allocation))
        reward -= 0.5 * allocation_change
        
        # Special condition handling
        if state['is_emergency']:
            # Reward for prioritizing URLLC during emergency
            reward += 3.0 * next_allocation[1]  # URLLC allocation
        
        if state['is_special_event']:
            # Reward for prioritizing eMBB during special events
            reward += 3.0 * next_allocation[0]  # eMBB allocation
        
        if state['is_iot_surge']:
            # Reward for prioritizing mMTC during IoT surges
            reward += 3.0 * next_allocation[2]  # mMTC allocation
        
        return reward
    
    def preprocess_state(self, state_dict):
        """Preprocess state dictionary into vector for DQN.
        
        Args:
            state_dict (dict): State dictionary
            
        Returns:
            numpy.ndarray: State vector
        """
        # Extract features from state dictionary
        features = state_dict['features']
        
        # Add additional information
        violations = state_dict['violations'].astype(float)
        is_emergency = float(state_dict['is_emergency'])
        is_special_event = float(state_dict['is_special_event'])
        is_iot_surge = float(state_dict['is_iot_surge'])
        
        # Combine into state vector
        state = np.concatenate([
            features,
            violations,
            [is_emergency, is_special_event, is_iot_surge]
        ])
        
        return state
    
    def action_to_allocation(self, action):
        """Convert discrete action to allocation.
        
        The action space is discretized into 27 actions:
        - Each slice can have low (0.1-0.3), medium (0.3-0.5), or high (0.5-0.7) allocation
        - 3^3 = 27 possible combinations
        
        Args:
            action (int): Discrete action (0-26)
            
        Returns:
            numpy.ndarray: Allocation vector [eMBB, URLLC, mMTC]
        """
        # Convert action to indices
        embb_idx = action // 9
        urllc_idx = (action % 9) // 3
        mmtc_idx = action % 3
        
        # Convert indices to allocation values
        embb_values = [0.2, 0.4, 0.6]
        urllc_values = [0.2, 0.4, 0.6]
        mmtc_values = [0.2, 0.4, 0.6]
        
        allocation = np.array([
            embb_values[embb_idx],
            urllc_values[urllc_idx],
            mmtc_values[mmtc_idx]
        ])
        
        # Normalize to ensure sum = 1
        allocation = allocation / np.sum(allocation)
        
        return allocation


# Example usage if script is run directly
if __name__ == "__main__":
    # Create agent
    agent = DQNAgent()
    
    # Create sample state
    state = np.random.random(14)
    
    # Get action
    action = agent.get_action(state)
    print(f"Action: {action}")
    
    # Convert to allocation
    allocation = agent.action_to_allocation(action)
    print(f"Allocation: {allocation}")
    
    # Create sample next state
    next_state = np.random.random(14)
    
    # Store transition
    agent.store_transition(state, action, 1.0, next_state, False)
    
    # Train step
    loss = agent.train_step()
    print(f"Loss: {loss}")
    
    # Save model
    agent.save_model("dqn_model.h5") 