# 📋 Commands Reference - Chaos Engineering Framework

## 🔍 Discovery Commands

### List Resources
```bash
# List all pods in default namespace
python3 main.py pod list

# List all nodes in cluster  
python3 main.py node list

# Show framework help
python3 main.py --help

# Show command-specific help
python3 main.py <command> --help
```

## 💥 Failure Injection Commands

### Pod-Level Failures
```bash
# Kill specific pod
python3 main.py pod kill <pod-name>

# Restart pod  
python3 main.py pod restart <pod-name>

# CPU stress test
python3 main.py pod cpu-stress <pod-name> --cpu-percent 80 --duration 60

# Memory stress test
python3 main.py pod memory-stress <pod-name> --memory-mb 512 --duration 60
```

### Node-Level Failures
```bash
# Drain node (move pods to other nodes)
python3 main.py node drain <node-name>

# Note: Node reboot is simulated in reliability tests
```

### Process-Level Failures
```bash
# Check available process commands
python3 main.py process --help
```

## 🔬 Reliability Simulation Commands

### Quick Tests
```bash
# Standard reliability test (500h simulated, ~5min real)
python3 main.py reliability test

# Show reliability options
python3 main.py reliability --help
```

### Custom Simulations
```bash
# Custom duration and acceleration
python3 main.py reliability start --duration 2 --acceleration 100

# With custom CSV output
python3 main.py reliability start --duration 1 --acceleration 24 --csv-path my_test.csv

# Specific namespace
python3 main.py reliability start --namespace production --duration 0.5 --acceleration 50
```

### Analysis Commands
```bash
# Analyze existing CSV file
python3 main.py reliability analyze results.csv

# Show reliability test help
python3 main.py reliability start --help
```

## 📊 Metrics & Monitoring Commands

### Reports Generation
```bash
# Generate comprehensive metrics report
python3 main.py metrics report

# Generate visualizations
python3 main.py metrics visualize

# Show metrics options
python3 main.py metrics --help
```

### System Monitoring
```bash
# Check monitoring options
python3 main.py monitor --help
```

## ⚙️ Configuration Commands

### Config Management
```bash
# Show current configuration
python3 main.py config show

# Set configuration value
python3 main.py config set <key> <value>

# Show config options
python3 main.py config --help
```

## 🎯 Scenario Commands

### Predefined Scenarios
```bash
# Run predefined chaos scenario
python3 main.py scenario run <scenario-name>

# List available scenarios
python3 main.py scenario list

# Show scenario options
python3 main.py scenario --help
```

## 🔧 Global Options

### Verbose Output
```bash
# Enable verbose logging
python3 main.py -v <command>

# Use custom config file
python3 main.py -c /path/to/config.yaml <command>
```

## 📋 Command Categories Summary

| Category | Command | Purpose |
|----------|---------|---------|
| **Discovery** | `pod list` | List available pods |
| | `node list` | List available nodes |
| **Pod Failures** | `pod kill` | Terminate pod |
| | `pod restart` | Restart pod |
| | `pod cpu-stress` | CPU stress test |
| | `pod memory-stress` | Memory stress test |
| **Node Failures** | `node drain` | Drain node |
| **Reliability** | `reliability test` | Quick reliability test |
| | `reliability start` | Custom simulation |
| | `reliability analyze` | Analyze results |
| **Metrics** | `metrics report` | Generate report |
| | `metrics visualize` | Create visualizations |
| **Config** | `config show` | Show configuration |
| | `config set` | Set configuration |
| **Scenarios** | `scenario run` | Run scenario |

## 🎨 Output Formats

### Table Output (Lists)
- Pod lists: Name, Node, Status
- Node lists: Name, Status, Role
- Colored status indicators (✅ ❌)

### Progress Output (Simulations)
- Real-time progress bars
- Simulated time tracking
- Failure counters
- Recovery monitoring

### Report Output (Analysis)
- JSON format reports
- CSV data exports
- Statistical summaries
- MTTF/MTBF/MTTR metrics

---
**📚 Complete Command Reference for Kubernetes Chaos Engineering Framework**