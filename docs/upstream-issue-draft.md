# Deleting an element leaves a dangling reference in operations: the deleted shape still gets engraved

**Your Operating System:** Windows 11

## Summary

Deleting an element from the elements tree doesn't remove it from the operations it was assigned to. The operation keeps a reference node pointing at the deleted element, so the shape still appears in the simulation and the machine still engraves it.

