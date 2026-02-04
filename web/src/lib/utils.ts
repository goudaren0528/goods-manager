import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const RENT_DAYS = [1, 2, 3, 4, 5, 7, 10, 15, 30, 60, 90];

export function getRentInfo(sku: any) {
    const anomalyDays = new Set<number>();
    
    // Convert to numbers
    const rents = new Map<number, number>();
    RENT_DAYS.forEach(d => {
        const val = Number(sku[`${d}天租金`]);
        if (!isNaN(val) && val > 0) {
            rents.set(d, val);
        }
    });

    // Check anomalies
    const sortedDays = Array.from(rents.keys()).sort((a, b) => a - b);
    
    for (let i = 0; i < sortedDays.length; i++) {
        const currentDay = sortedDays[i];
        const currentRent = rents.get(currentDay)!;
        const currentDaily = currentRent / currentDay;
        
        // Find valid neighbors
        let prevDaily = Infinity;
        let nextDaily = Infinity;
        
        if (i > 0) {
            const prevDay = sortedDays[i-1];
            prevDaily = rents.get(prevDay)! / prevDay;
        }
        
        if (i < sortedDays.length - 1) {
            const nextDay = sortedDays[i+1];
            nextDaily = rents.get(nextDay)! / nextDay;
        }
        
        // Condition: strictly lower than BOTH neighbors (if they exist)
        // If only one neighbor exists, compare with that one.
        // The requirement says "lower than both its immediate valid neighbors". 
        // If it's an edge (first or last), it only has one neighbor. 
        // Strict interpretation: "both" implies it must have two neighbors to be anomalous?
        // Or "all existing neighbors"?
        // Let's assume "all existing neighbors".
        
        let isLower = true;
        if (i > 0 && currentDaily >= prevDaily) isLower = false;
        if (i < sortedDays.length - 1 && currentDaily >= nextDaily) isLower = false;
        
        // If it's a single point, it's not lower than anything
        if (sortedDays.length === 1) isLower = false;
        
        if (isLower) {
            anomalyDays.add(currentDay);
        }
    }
    
    return { anomalyDays };
}
