"""Coverage-aware 1D CFD profile comparison."""
from .core import Profile, ProfileError, audit, load_csv, sample
__all__ = ['Profile','ProfileError','audit','load_csv','sample']
__version__ = '0.1.0rc1'
