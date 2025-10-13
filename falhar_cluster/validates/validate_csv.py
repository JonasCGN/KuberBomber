#!/usr/bin/env python3
"""
🔍 CSV Validation Script for Chaos Engineering Framework
Validates and analyzes reliability simulation CSV files.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import argparse
import json
from pathlib import Path
import sys

class CSVValidator:
    def __init__(self, csv_path):
        self.csv_path = Path(csv_path)
        self.df = None
        self.validation_results = {
            'file_info': {},
            'data_quality': {},
            'metrics': {},
            'statistics': {},
            'anomalies': [],
            'recommendations': []
        }
    
    def load_data(self):
        """Load and initial validation of CSV file"""
        try:
            self.df = pd.read_csv(self.csv_path)
            self.validation_results['file_info'] = {
                'file_path': str(self.csv_path),
                'file_size_mb': round(self.csv_path.stat().st_size / (1024*1024), 2),
                'total_rows': len(self.df),
                'columns': list(self.df.columns),
                'loaded_successfully': True
            }
            print(f"✅ CSV loaded successfully: {len(self.df)} rows, {len(self.df.columns)} columns")
            return True
        except Exception as e:
            print(f"❌ Error loading CSV: {e}")
            self.validation_results['file_info']['error'] = str(e)
            return False
    
    def validate_structure(self):
        """Validate CSV structure and required columns"""
        print("\n🔍 Validating CSV structure...")
        
        required_columns = [
            'timestamp', 'simulation_time_hours', 'real_time_seconds', 
            'event_type', 'failure_mode', 'target', 'target_type'
        ]
        
        missing_columns = [col for col in required_columns if col not in self.df.columns]
        
        self.validation_results['data_quality']['required_columns'] = {
            'missing': missing_columns,
            'present': [col for col in required_columns if col in self.df.columns],
            'valid': len(missing_columns) == 0
        }
        
        if missing_columns:
            print(f"❌ Missing required columns: {missing_columns}")
            return False
        else:
            print("✅ All required columns present")
            return True
    
    def validate_data_types(self):
        """Validate data types and formats"""
        print("\n🔍 Validating data types...")
        
        # Convert timestamp to datetime
        try:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
            print("✅ Timestamp format valid")
        except Exception as e:
            print(f"❌ Invalid timestamp format: {e}")
            self.validation_results['anomalies'].append(f"Invalid timestamp format: {e}")
        
        # Validate numeric columns
        numeric_cols = ['simulation_time_hours', 'real_time_seconds', 'duration_seconds']
        for col in numeric_cols:
            if col in self.df.columns:
                try:
                    self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
                    null_count = self.df[col].isnull().sum()
                    if null_count > 0:
                        print(f"⚠️  {col}: {null_count} invalid numeric values converted to NaN")
                    else:
                        print(f"✅ {col}: All values are numeric")
                except Exception as e:
                    print(f"❌ Error validating {col}: {e}")
    
    def analyze_timeline(self):
        """Analyze simulation timeline and continuity"""
        print("\n📊 Analyzing timeline...")
        
        if 'timestamp' not in self.df.columns:
            return
        
        # Sort by timestamp
        self.df = self.df.sort_values('timestamp')
        
        # Timeline analysis
        start_time = self.df['timestamp'].min()
        end_time = self.df['timestamp'].max()
        duration = end_time - start_time
        
        timeline_info = {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_duration': str(duration),
            'duration_seconds': duration.total_seconds()
        }
        
        self.validation_results['metrics']['timeline'] = timeline_info
        
        print(f"📅 Simulation period: {start_time} to {end_time}")
        print(f"⏱️  Total duration: {duration}")
        
        # Check for time gaps
        time_diffs = self.df['timestamp'].diff()
        large_gaps = time_diffs[time_diffs > timedelta(minutes=5)]
        
        if len(large_gaps) > 0:
            print(f"⚠️  Found {len(large_gaps)} time gaps > 5 minutes")
            self.validation_results['anomalies'].append(f"Large time gaps detected: {len(large_gaps)} gaps")
    
    def analyze_failures(self):
        """Analyze failure patterns and statistics"""
        print("\n💥 Analyzing failures...")
        
        # Event type distribution
        event_counts = self.df['event_type'].value_counts()
        print("\n📊 Event distribution:")
        for event, count in event_counts.items():
            print(f"  {event}: {count}")
        
        # Failure type analysis
        failures_df = self.df[self.df['event_type'] == 'failure_initiated'].copy()
        if len(failures_df) > 0:
            failure_types = failures_df['failure_mode'].value_counts()
            print("\n🎯 Failure types:")
            for failure_type, count in failure_types.items():
                print(f"  {failure_type}: {count}")
            
            # Target analysis
            target_types = failures_df['target_type'].value_counts()
            print("\n🎯 Target types:")
            for target_type, count in target_types.items():
                print(f"  {target_type}: {count}")
        
        self.validation_results['statistics']['failures'] = {
            'total_failure_events': len(failures_df),
            'failure_types': failure_types.to_dict() if len(failures_df) > 0 else {},
            'target_types': target_types.to_dict() if len(failures_df) > 0 else {},
            'event_distribution': event_counts.to_dict()
        }
    
    def analyze_recovery_times(self):
        """Analyze recovery time patterns"""
        print("\n🔄 Analyzing recovery times...")
        
        recovery_df = self.df[self.df['event_type'] == 'recovery_completed'].copy()
        
        if len(recovery_df) == 0:
            print("❌ No recovery events found")
            return
        
        if 'duration_seconds' in recovery_df.columns:
            recovery_times = recovery_df['duration_seconds'].dropna()
            
            if len(recovery_times) > 0:
                recovery_stats = {
                    'count': len(recovery_times),
                    'mean_seconds': float(recovery_times.mean()),
                    'median_seconds': float(recovery_times.median()),
                    'std_seconds': float(recovery_times.std()),
                    'min_seconds': float(recovery_times.min()),
                    'max_seconds': float(recovery_times.max()),
                    'q25_seconds': float(recovery_times.quantile(0.25)),
                    'q75_seconds': float(recovery_times.quantile(0.75))
                }
                
                self.validation_results['statistics']['recovery_times'] = recovery_stats
                
                print(f"📊 Recovery time statistics ({len(recovery_times)} events):")
                print(f"  Mean: {recovery_stats['mean_seconds']:.2f}s")
                print(f"  Median: {recovery_stats['median_seconds']:.2f}s")
                print(f"  Std Dev: {recovery_stats['std_seconds']:.2f}s")
                print(f"  Range: {recovery_stats['min_seconds']:.2f}s - {recovery_stats['max_seconds']:.2f}s")
                
                # Detect outliers
                q1 = recovery_stats['q25_seconds']
                q3 = recovery_stats['q75_seconds']
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                
                outliers = recovery_times[(recovery_times < lower_bound) | (recovery_times > upper_bound)]
                
                if len(outliers) > 0:
                    print(f"⚠️  Found {len(outliers)} recovery time outliers")
                    self.validation_results['anomalies'].append(f"Recovery time outliers: {len(outliers)} events")
    
    def analyze_mttf_mtbf_mttr(self):
        """Analyze MTTF, MTBF, MTTR metrics"""
        print("\n📈 Analyzing MTTF/MTBF/MTTR metrics...")
        
        # Get final metrics from last row
        last_row = self.df.iloc[-1]
        
        metrics = {}
        for metric in ['mttf_hours', 'mtbf_hours', 'mttr_seconds']:
            if metric in last_row and pd.notna(last_row[metric]):
                metrics[metric] = float(last_row[metric])
        
        if metrics:
            self.validation_results['metrics']['reliability'] = metrics
            
            print("📊 Final reliability metrics:")
            if 'mttf_hours' in metrics:
                print(f"  MTTF: {metrics['mttf_hours']:.2f} hours")
            if 'mtbf_hours' in metrics:
                print(f"  MTBF: {metrics['mtbf_hours']:.2f} hours")
            if 'mttr_seconds' in metrics:
                print(f"  MTTR: {metrics['mttr_seconds']:.2f} seconds")
        else:
            print("❌ No reliability metrics found in final row")
            self.validation_results['anomalies'].append("Missing reliability metrics")
    
    def analyze_simulation_acceleration(self):
        """Analyze simulation acceleration and timing"""
        print("\n⚡ Analyzing simulation acceleration...")
        
        if 'simulation_time_hours' in self.df.columns and 'real_time_seconds' in self.df.columns:
            # Calculate acceleration factor
            sim_hours = self.df['simulation_time_hours'].max()
            real_seconds = self.df['real_time_seconds'].max()
            real_hours = real_seconds / 3600
            
            if real_hours > 0:
                acceleration = sim_hours / real_hours
                
                acceleration_info = {
                    'simulated_hours': float(sim_hours),
                    'real_seconds': float(real_seconds),
                    'real_hours': float(real_hours),
                    'acceleration_factor': float(acceleration)
                }
                
                self.validation_results['metrics']['acceleration'] = acceleration_info
                
                print(f"⚡ Acceleration analysis:")
                print(f"  Simulated time: {sim_hours:.2f} hours")
                print(f"  Real time: {real_hours:.2f} hours ({real_seconds:.2f} seconds)")
                print(f"  Acceleration factor: {acceleration:.1f}x")
    
    def detect_anomalies(self):
        """Detect data anomalies and inconsistencies"""
        print("\n🚨 Detecting anomalies...")
        
        anomaly_count = 0
        
        # Check for duplicate failure IDs
        if 'failure_id' in self.df.columns:
            failure_ids = self.df[self.df['failure_id'].notna()]['failure_id']
            duplicates = failure_ids[failure_ids.duplicated()]
            if len(duplicates) > 0:
                anomaly_count += len(duplicates)
                self.validation_results['anomalies'].append(f"Duplicate failure IDs: {len(duplicates)}")
                print(f"⚠️  Found {len(duplicates)} duplicate failure IDs")
        
        # Check for negative durations
        if 'duration_seconds' in self.df.columns:
            negative_durations = self.df[self.df['duration_seconds'] < 0]
            if len(negative_durations) > 0:
                anomaly_count += len(negative_durations)
                self.validation_results['anomalies'].append(f"Negative durations: {len(negative_durations)}")
                print(f"⚠️  Found {len(negative_durations)} negative duration values")
        
        # Check for missing targets in failure events
        failure_events = self.df[self.df['event_type'] == 'failure_initiated']
        missing_targets = failure_events[failure_events['target'].isna() | (failure_events['target'] == '')]
        if len(missing_targets) > 0:
            anomaly_count += len(missing_targets)
            self.validation_results['anomalies'].append(f"Missing targets in failures: {len(missing_targets)}")
            print(f"⚠️  Found {len(missing_targets)} failure events with missing targets")
        
        if anomaly_count == 0:
            print("✅ No significant anomalies detected")
        else:
            print(f"⚠️  Total anomalies detected: {anomaly_count}")
    
    def generate_recommendations(self):
        """Generate recommendations based on analysis"""
        print("\n💡 Generating recommendations...")
        
        recommendations = []
        
        # Check data completeness
        if len(self.validation_results['anomalies']) > 0:
            recommendations.append("Review and clean data anomalies before using for analysis")
        
        # Check simulation duration
        if 'acceleration' in self.validation_results['metrics']:
            sim_hours = self.validation_results['metrics']['acceleration']['simulated_hours']
            if sim_hours < 100:
                recommendations.append("Consider longer simulation duration for more reliable statistics")
            elif sim_hours > 1000:
                recommendations.append("Simulation duration is good for statistical analysis")
        
        # Check failure count
        if 'failures' in self.validation_results['statistics']:
            failure_count = self.validation_results['statistics']['failures']['total_failure_events']
            if failure_count < 50:
                recommendations.append("Low failure count - consider longer simulation or higher failure rate")
            elif failure_count > 100:
                recommendations.append("Good failure count for statistical analysis")
        
        # Check recovery times
        if 'recovery_times' in self.validation_results['statistics']:
            recovery_stats = self.validation_results['statistics']['recovery_times']
            if recovery_stats['std_seconds'] > recovery_stats['mean_seconds']:
                recommendations.append("High variability in recovery times - investigate causes")
        
        self.validation_results['recommendations'] = recommendations
        
        print("💡 Recommendations:")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
    
    def create_visualizations(self, output_dir=None):
        """Create validation visualizations"""
        print("\n📊 Creating visualizations...")
        
        if output_dir is None:
            output_dir = Path("validation_plots")
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(exist_ok=True)
        
        # Set style
        plt.style.use('seaborn-v0_8')
        
        # 1. Timeline plot
        if 'timestamp' in self.df.columns:
            plt.figure(figsize=(12, 6))
            event_counts = self.df.groupby([self.df['timestamp'].dt.floor('T'), 'event_type']).size().unstack(fill_value=0)
            event_counts.plot(kind='bar', stacked=True, ax=plt.gca())
            plt.title('Events Timeline (per minute)')
            plt.xlabel('Time')
            plt.ylabel('Event Count')
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig(output_dir / 'timeline.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # 2. Recovery time distribution
        recovery_df = self.df[self.df['event_type'] == 'recovery_completed']
        if len(recovery_df) > 0 and 'duration_seconds' in recovery_df.columns:
            plt.figure(figsize=(10, 6))
            recovery_times = recovery_df['duration_seconds'].dropna()
            
            plt.subplot(1, 2, 1)
            plt.hist(recovery_times, bins=20, alpha=0.7, color='skyblue')
            plt.title('Recovery Time Distribution')
            plt.xlabel('Duration (seconds)')
            plt.ylabel('Frequency')
            
            plt.subplot(1, 2, 2)
            plt.boxplot(recovery_times)
            plt.title('Recovery Time Box Plot')
            plt.ylabel('Duration (seconds)')
            
            plt.tight_layout()
            plt.savefig(output_dir / 'recovery_times.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # 3. Failure type distribution
        failures_df = self.df[self.df['event_type'] == 'failure_initiated']
        if len(failures_df) > 0:
            plt.figure(figsize=(12, 8))
            
            plt.subplot(2, 2, 1)
            failure_types = failures_df['failure_mode'].value_counts()
            plt.pie(failure_types.values, labels=failure_types.index, autopct='%1.1f%%')
            plt.title('Failure Types Distribution')
            
            plt.subplot(2, 2, 2)
            target_types = failures_df['target_type'].value_counts()
            plt.pie(target_types.values, labels=target_types.index, autopct='%1.1f%%')
            plt.title('Target Types Distribution')
            
            plt.subplot(2, 2, 3)
            failures_per_target = failures_df['target'].value_counts().head(10)
            plt.bar(range(len(failures_per_target)), failures_per_target.values)
            plt.title('Top 10 Targets by Failure Count')
            plt.xlabel('Target')
            plt.ylabel('Failure Count')
            plt.xticks(range(len(failures_per_target)), failures_per_target.index, rotation=45)
            
            plt.tight_layout()
            plt.savefig(output_dir / 'failure_analysis.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        print(f"📊 Visualizations saved to: {output_dir}")
    
    def save_validation_report(self, output_path=None):
        """Save validation report to JSON"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"csv_validation_report_{timestamp}.json"
        
        with open(output_path, 'w') as f:
            json.dump(self.validation_results, f, indent=2, default=str)
        
        print(f"📄 Validation report saved to: {output_path}")
        return output_path
    
    def run_full_validation(self, create_plots=True, save_report=True):
        """Run complete validation pipeline"""
        print("🔍 Starting CSV validation...")
        
        if not self.load_data():
            return False
        
        if not self.validate_structure():
            return False
        
        self.validate_data_types()
        self.analyze_timeline()
        self.analyze_failures()
        self.analyze_recovery_times()
        self.analyze_mttf_mtbf_mttr()
        self.analyze_simulation_acceleration()
        self.detect_anomalies()
        self.generate_recommendations()
        
        if create_plots:
            self.create_visualizations()
        
        if save_report:
            self.save_validation_report()
        
        print("\n✅ Validation completed successfully!")
        return True

def main():
    parser = argparse.ArgumentParser(description='Validate Chaos Engineering CSV files')
    parser.add_argument('csv_file', help='Path to CSV file to validate')
    parser.add_argument('--no-plots', action='store_true', help='Skip plot generation')
    parser.add_argument('--no-report', action='store_true', help='Skip report generation')
    parser.add_argument('--output-dir', help='Output directory for plots')
    
    args = parser.parse_args()
    
    if not Path(args.csv_file).exists():
        print(f"❌ File not found: {args.csv_file}")
        sys.exit(1)
    
    validator = CSVValidator(args.csv_file)
    
    success = validator.run_full_validation(
        create_plots=not args.no_plots,
        save_report=not args.no_report
    )
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()