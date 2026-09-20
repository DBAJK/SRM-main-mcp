"""
5G Network Slicing - AI Components

This subpackage contains AI components for the 5G network slicing system,
including models, slice managers, and training utilities.
"""

from .lstm_predictor import SliceAllocationPredictor
from .dqn_classifier import TrafficClassifier

__all__ = ['SliceAllocationPredictor', 'TrafficClassifier'] 