#!/usr/bin/env python3
"""
DQN-based Traffic Classifier

This module provides a DQN-based classifier for identifying optimal 
network slice types based on traffic patterns and network conditions.
"""

import os
import random
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import tensorflow as tf
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense, Dropout, BatchNormalization
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping
from collections import deque

class TrafficClassifier:
    """Classifies network traffic to determine optimal slice types"""
    
    def __init__(self, input_dim=11, output_dim=3, model_path=None):
        """Initialize the traffic classifier
        
        Args:
            input_dim (int): Dimension of input features
            output_dim (int): Number of output classes (slice types)
            model_path (str): Path to load model from
        """
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.model_path = model_path
        self.training_history = None
        
        # DQN parameters
        self.memory = deque(maxlen=20000)  # Increased memory size
        self.gamma = 0.95  # discount factor
        self.epsilon = 1.0  # exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        
        # Class names
        self.class_names = ['eMBB', 'URLLC', 'mMTC']
        
        # Initialize model
        if model_path and os.path.exists(model_path):
            try:
                self.model = load_model(model_path)
                print(f"Loaded DQN model from {model_path}")
            except Exception as e:
                print(f"Error loading model: {e}")
                self.model = self._build_model()
        else:
            self.model = self._build_model()
            
            # If no pre-trained model, train on synthetic data
            print("Training DQN classifier on synthetic data...")
            X_train, y_train, X_val, y_val = self._generate_training_data(15000)  # Increased to 15,000 samples
            self.training_history = self.train(X_train, y_train, epochs=150, batch_size=64, validation_data=(X_val, y_val))
            val_loss = self.training_history.history['val_loss'][-1]
            val_acc = self.training_history.history['val_accuracy'][-1]
            print(f"Training completed. Validation Loss: {val_loss:.4f}, Validation Accuracy: {val_acc:.4f}")
    
    def _build_model(self):
        """Build the DQN model
        
        Returns:
            keras.Model: Compiled model
        """
        # Print model architecture
        print("DQN Traffic Classifier Architecture:")
        
        model = Sequential([
            # Input layer
            Dense(128, input_dim=self.input_dim, activation='relu'),
            BatchNormalization(),
            Dropout(0.3),
            
            # Hidden layers
            Dense(64, activation='relu'),
            BatchNormalization(),
            Dropout(0.3),
            
            Dense(32, activation='relu'),
            BatchNormalization(),
            Dropout(0.2),
            
            # Output layer (one neuron per slice type)
            Dense(self.output_dim, activation='softmax')
        ])
        
        # Compile model
        model.compile(
            optimizer=Adam(learning_rate=self.learning_rate),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        
        # Print model summary
        model.summary()
        
        return model
    
    def _generate_training_data(self, num_samples=15000):
        """Generate synthetic training data
        
        Args:
            num_samples (int): Number of samples to generate
            
        Returns:
            tuple: (X_train, y_train, X_val, y_val)
        """
        # Generate synthetic data for different traffic patterns
        # Input features: [traffic_load, time_of_day, day_of_week, embb_alloc, urllc_alloc, mmtc_alloc, 
        #                  embb_util, urllc_util, mmtc_util, client_count, bs_count]
        
        X = np.zeros((num_samples, self.input_dim))
        y = np.zeros((num_samples, self.output_dim))
        
        # Different scenarios and their likelihood
        scenarios = ['eMBB_dominant', 'URLLC_dominant', 'mMTC_dominant', 'mixed', 'balanced']
        scenario_probs = [0.3, 0.25, 0.25, 0.1, 0.1]
        
        for i in range(num_samples):
            # Generate random network state
            time_of_day = np.random.uniform(0, 1)  # Normalized time of day
            day_of_week = np.random.uniform(0, 1)  # Normalized day of week
            
            # Generate traffic_load based partly on time of day (busier during work hours)
            time_factor = 0.3 * np.sin(time_of_day * 2 * np.pi - np.pi/2) + 0.5  # Peak at mid-day
            day_factor = 0.1 * (0.5 - np.abs(day_of_week - 0.5))  # Midweek slightly busier
            base_traffic = 0.3 + time_factor + day_factor
            traffic_load = base_traffic + 0.3 * np.random.randn()
            traffic_load = np.clip(traffic_load, 0.1, 2.0)
            
            # Current allocations (sum to 1)
            current_allocation = np.random.dirichlet(np.ones(3) * 3)  # Less extreme allocations
            
            # Determine scenario for this sample
            scenario = np.random.choice(scenarios, p=scenario_probs)
            
            # Generate utilization patterns based on scenario
            slice_utilization = np.zeros(3)
            client_count = 0.0
            
            if scenario == 'eMBB_dominant':
                # High bandwidth applications
                slice_utilization[0] = np.random.uniform(0.9, 2.0)  # eMBB high utilization
                slice_utilization[1] = np.random.uniform(0.1, 0.7)  # URLLC moderate-low utilization
                slice_utilization[2] = np.random.uniform(0.1, 0.5)  # mMTC low utilization
                
                # Client count - moderate number of high-bandwidth clients
                client_count = np.random.uniform(0.4, 0.8)
                
                # Set eMBB as target class
                y[i, 0] = 1
                
            elif scenario == 'URLLC_dominant':
                # Low latency requirements (emergency, critical services)
                slice_utilization[0] = np.random.uniform(0.2, 0.8)  # eMBB moderate utilization
                slice_utilization[1] = np.random.uniform(0.8, 2.0)  # URLLC high utilization
                slice_utilization[2] = np.random.uniform(0.1, 0.4)  # mMTC low utilization
                
                # Client count - can vary, often fewer clients but critical
                client_count = np.random.uniform(0.3, 0.7)
                
                # Set URLLC as target class
                y[i, 1] = 1
                
            elif scenario == 'mMTC_dominant':
                # Massive IoT deployments
                slice_utilization[0] = np.random.uniform(0.1, 0.5)  # eMBB low utilization
                slice_utilization[1] = np.random.uniform(0.1, 0.6)  # URLLC low-moderate utilization
                slice_utilization[2] = np.random.uniform(0.8, 2.0)  # mMTC high utilization
                
                # Client count - many small devices
                client_count = np.random.uniform(0.7, 1.0)
                
                # Set mMTC as target class
                y[i, 2] = 1
                
            elif scenario == 'mixed':
                # Mixed traffic with two types having significant presence
                primary = np.random.randint(0, 3)
                secondary = (primary + 1 + np.random.randint(0, 2)) % 3  # Not the same as primary
                
                # Set utilization - primary high, secondary moderate, tertiary low
                slice_utilization = np.array([0.3, 0.3, 0.3])  # Base values
                slice_utilization[primary] = np.random.uniform(0.8, 1.5)
                slice_utilization[secondary] = np.random.uniform(0.5, 1.0)
                
                # Client count depends on which slices are active
                if primary == 2 or secondary == 2:  # mMTC involved
                    client_count = np.random.uniform(0.6, 0.9)
                else:
                    client_count = np.random.uniform(0.4, 0.7)
                
                # Set target class as primary type
                y[i, primary] = 1
                
            else:  # balanced
                # More evenly balanced traffic
                base_util = np.random.uniform(0.4, 0.8)
                variation = np.random.uniform(0.1, 0.3, 3)
                slice_utilization = base_util + variation
                
                # Client count - moderate
                client_count = np.random.uniform(0.5, 0.8)
                
                # Determine dominant class (even if only slightly)
                dominant_class = np.argmax(slice_utilization)
                y[i, dominant_class] = 1
            
            # Generate base station count (partially correlated with client count)
            bs_count = 0.3 + 0.4 * client_count + 0.2 * np.random.random()
            bs_count = np.clip(bs_count, 0.2, 1.0)
            
            # Time-based modifications
            # Late night has more mMTC activity, less eMBB
            if time_of_day < 0.25 or time_of_day > 0.9:  # Late night/early morning
                slice_utilization[0] *= 0.7  # Reduce eMBB
                slice_utilization[2] *= 1.3  # Increase mMTC
            
            # Business hours have more eMBB activity
            if 0.35 < time_of_day < 0.65:  # Business hours
                slice_utilization[0] *= 1.2  # Increase eMBB
            
            # Create feature vector
            X[i] = np.array([
                traffic_load,
                time_of_day,
                day_of_week,
                current_allocation[0],  # eMBB
                current_allocation[1],  # URLLC
                current_allocation[2],  # mMTC
                slice_utilization[0],   # eMBB utilization
                slice_utilization[1],   # URLLC utilization
                slice_utilization[2],   # mMTC utilization
                client_count,
                bs_count
            ])
            
            # Add some noise to make classification more challenging but realistic
            X[i] += np.random.normal(0, 0.03, self.input_dim)
            
            # Clip features to valid ranges
            X[i] = np.clip(X[i], 0, 2)
        
        # Split into training and validation sets (80/20)
        split_idx = int(0.8 * num_samples)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        print(f"Generated {len(X_train)} training samples and {len(X_val)} validation samples")
        
        return X_train, y_train, X_val, y_val
    
    def remember(self, state, action, reward, next_state, done):
        """Store experience in replay memory
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether the episode is done
        """
        self.memory.append((state, action, reward, next_state, done))
    
    def act(self, state):
        """Choose an action using epsilon-greedy policy
        
        Args:
            state: Current state
            
        Returns:
            int: Selected action
        """
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.output_dim)
        
        act_values = self.model.predict(state.reshape(1, -1))
        return np.argmax(act_values[0])
    
    def replay(self, batch_size):
        """Train model on a batch of experiences
        
        Args:
            batch_size (int): Size of training batch
        """
        if len(self.memory) < batch_size:
            return
        
        minibatch = random.sample(self.memory, batch_size)
        states = np.array([i[0] for i in minibatch])
        actions = np.array([i[1] for i in minibatch])
        rewards = np.array([i[2] for i in minibatch])
        next_states = np.array([i[3] for i in minibatch])
        dones = np.array([i[4] for i in minibatch])
        
        # Batch prediction to improve performance
        states_batch = np.vstack(states)
        next_states_batch = np.vstack(next_states)
        
        # Predict current Q values and next Q values
        current_q = self.model.predict(states_batch)
        target_q = current_q.copy()
        next_q = self.model.predict(next_states_batch)
        
        # Update target Q values
        for i, (_, action, reward, _, done) in enumerate(minibatch):
            if done:
                target_q[i, action] = reward
            else:
                target_q[i, action] = reward + self.gamma * np.amax(next_q[i])
        
        # Train model
        self.model.fit(states_batch, target_q, epochs=1, verbose=0)
        
        # Update epsilon for exploration
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
    
    def train(self, X_train, y_train, epochs=150, batch_size=64, validation_data=None):
        """Train the model using supervised learning
        
        Args:
            X_train (numpy.ndarray): Training features
            y_train (numpy.ndarray): Training labels
            epochs (int): Number of training epochs
            batch_size (int): Batch size
            validation_data (tuple): Validation data (X_val, y_val)
            
        Returns:
            keras.callbacks.History: Training history
        """
        # Early stopping to prevent overfitting
        early_stopping = EarlyStopping(
            monitor='val_loss' if validation_data else 'loss',
            patience=15,
            restore_best_weights=True
        )
        
        # Train model
        history = self.model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=validation_data,
            callbacks=[early_stopping],
            verbose=1  # Show progress bar
        )
        
        return history
    
    def classify(self, features):
        """Classify traffic based on input features
        
        Args:
            features (numpy.ndarray): Input features
            
        Returns:
            tuple: (class_index, class_probabilities)
        """
        # Reshape features if needed
        if len(features.shape) == 1:
            features = features.reshape(1, -1)
        
        # Get class probabilities
        class_probs = self.model.predict(features)
        
        # Get class with highest probability
        class_idx = np.argmax(class_probs, axis=1)
        
        return class_idx, class_probs
    
    def evaluate(self, X_test, y_test):
        """Evaluate the model
        
        Args:
            X_test (numpy.ndarray): Test features
            y_test (numpy.ndarray): Test labels
            
        Returns:
            tuple: (loss, accuracy)
        """
        return self.model.evaluate(X_test, y_test)
    
    def save(self, path=None):
        """Save the model
        
        Args:
            path (str): Path to save the model
        """
        if path is None:
            path = self.model_path or f"dqn_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        
        self.model.save(path)
        print(f"Model saved to {path}")
    
    def plot_training_history(self, history=None):
        """Plot training history
        
        Args:
            history (keras.callbacks.History): Training history
        """
        if history is None:
            history = self.training_history
            
        if history is None:
            print("No training history available")
            return
            
        plt.figure(figsize=(12, 5))
        
        # Plot loss
        plt.subplot(1, 2, 1)
        plt.plot(history.history['loss'], label='Training Loss')
        if 'val_loss' in history.history:
            plt.plot(history.history['val_loss'], label='Validation Loss')
        plt.title('Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.legend()
        
        # Plot accuracy
        plt.subplot(1, 2, 2)
        plt.plot(history.history['accuracy'], label='Training Accuracy')
        if 'val_accuracy' in history.history:
            plt.plot(history.history['val_accuracy'], label='Validation Accuracy')
        plt.title('Accuracy')
        plt.xlabel('Epoch')
        plt.ylabel('Accuracy')
        plt.legend()
        
        plt.tight_layout()
        plt.show()
    
    def get_class_name(self, class_idx):
        """Get class name from index
        
        Args:
            class_idx (int): Class index
            
        Returns:
            str: Class name
        """
        return self.class_names[class_idx]
    
    def analyze_feature_importance(self, X_test, y_test, num_permutations=10):
        """Analyze feature importance using permutation importance
        
        Args:
            X_test (numpy.ndarray): Test features
            y_test (numpy.ndarray): Test labels
            num_permutations (int): Number of permutations for each feature
            
        Returns:
            dict: Feature importance scores
        """
        # Get baseline accuracy
        _, baseline_accuracy = self.evaluate(X_test, y_test)
        
        # Feature names
        feature_names = [
            'Traffic Load', 'Time of Day', 'Day of Week',
            'eMBB Allocation', 'URLLC Allocation', 'mMTC Allocation',
            'eMBB Utilization', 'URLLC Utilization', 'mMTC Utilization',
            'Client Count', 'Base Station Count'
        ]
        
        # Calculate importance for each feature
        importance = {}
        for i, feature_name in enumerate(feature_names):
            # Create multiple permutations
            importance_scores = []
            
            for _ in range(num_permutations):
                # Copy test data
                X_permuted = X_test.copy()
                
                # Permute the feature
                np.random.shuffle(X_permuted[:, i])
                
                # Evaluate with permuted feature
                _, permuted_accuracy = self.evaluate(X_permuted, y_test)
                
                # Calculate importance (drop in accuracy)
                importance_score = baseline_accuracy - permuted_accuracy
                importance_scores.append(importance_score)
            
            # Average importance
            importance[feature_name] = np.mean(importance_scores)
        
        return importance


# Example usage if script is run directly
if __name__ == "__main__":
    # Create classifier
    classifier = TrafficClassifier()
    
    # Generate test data
    X_test, y_test, _, _ = classifier._generate_training_data(100)
    
    # Evaluate model
    loss, accuracy = classifier.evaluate(X_test, y_test)
    print(f"Test Loss: {loss:.4f}, Test Accuracy: {accuracy:.4f}")
    
    # Plot training history
    classifier.plot_training_history()
    
    # Make some predictions
    for i in range(5):
        sample_idx = np.random.randint(0, len(X_test))
        features = X_test[sample_idx]
        true_class = np.argmax(y_test[sample_idx])
        
        class_idx, class_probs = classifier.classify(features)
        
        print(f"\nSample {i+1}:")
        print(f"True class: {classifier.get_class_name(true_class)}")
        print(f"Predicted class: {classifier.get_class_name(class_idx[0])}")
        print(f"Class probabilities: eMBB={class_probs[0][0]:.2f}, URLLC={class_probs[0][1]:.2f}, mMTC={class_probs[0][2]:.2f}")
        
    # Plot some predictions
    plt.figure(figsize=(15, 8))
    for i in range(4):
        plt.subplot(2, 2, i+1)
        sample_idx = np.random.randint(0, len(X_test))
        
        # Get features and true class
        features = X_test[sample_idx]
        true_class = np.argmax(y_test[sample_idx])
        
        # Get prediction
        _, class_probs = classifier.classify(features)
        
        # Plot
        labels = ['eMBB', 'URLLC', 'mMTC']
        x = np.arange(len(labels))
        
        # Use different colors for the true class
        colors = ['lightblue', 'lightblue', 'lightblue']
        colors[true_class] = 'orange'
        
        plt.bar(x, class_probs[0], color=colors, alpha=0.8)
        plt.axhline(y=0.33, color='r', linestyle='--', label='Random guess')
        
        plt.ylabel('Probability')
        plt.title(f'True class: {labels[true_class]}')
        plt.xticks(x, labels)
        plt.ylim(0, 1)
        
        # Add value labels
        for j, v in enumerate(class_probs[0]):
            plt.text(j, v + 0.02, f'{v:.2f}', ha='center')
            
        plt.legend()
    
    plt.tight_layout()
    plt.show()
    
    # Analyze feature importance
    importance = classifier.analyze_feature_importance(X_test, y_test)
    
    # Plot feature importance
    plt.figure(figsize=(12, 6))
    features = list(importance.keys())
    scores = list(importance.values())
    
    # Sort by importance
    sorted_idx = np.argsort(scores)
    plt.barh(np.array(features)[sorted_idx], np.array(scores)[sorted_idx])
    plt.xlabel('Importance (drop in accuracy when permuted)')
    plt.title('Feature Importance for Traffic Classification')
    plt.tight_layout()
    plt.show() 